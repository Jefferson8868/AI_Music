"""
Magenta Music Engine Microservice
=================================
Runs in a SEPARATE Python 3.7 conda environment.

Setup:
    conda create -n magenta_env python=3.7
    conda activate magenta_env
    pip install magenta fastapi uvicorn

Download models:
    mkdir -p models/
    wget http://download.magenta.tensorflow.org/models/attention_rnn.mag -P models/
    wget http://download.magenta.tensorflow.org/models/polyphony_rnn.mag -P models/

Run:
    conda activate magenta_env
    uvicorn src.engine.magenta_service:app --port 8001
"""

import os
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Magenta Music Engine")

# Lazy-loaded generators (initialized on first request)
_melody_generator = None
_poly_generator = None
_initialized = False

MELODY_MODEL_PATH = os.environ.get("MELODY_MODEL", "./models/attention_rnn.mag")
POLY_MODEL_PATH = os.environ.get("POLY_MODEL", "./models/polyphony_rnn.mag")


class GenRequest(BaseModel):
    primer_notes: list = [60, 64, 67]
    num_steps: int = 128
    temperature: float = 1.0
    qpm: float = 120.0


def _init_generators():
    global _melody_generator, _poly_generator, _initialized
    if _initialized:
        return

    import magenta.music as mm
    from magenta.models.melody_rnn import melody_rnn_sequence_generator
    from magenta.models.polyphony_rnn import polyphony_rnn_sequence_generator
    from magenta.models.shared import sequence_generator_bundle

    if os.path.exists(MELODY_MODEL_PATH):
        bundle = sequence_generator_bundle.read_bundle_file(MELODY_MODEL_PATH)
        gen_map = melody_rnn_sequence_generator.get_generator_map()
        _melody_generator = gen_map["attention_rnn"](checkpoint=None, bundle=bundle)
        _melody_generator.initialize()

    if os.path.exists(POLY_MODEL_PATH):
        bundle = sequence_generator_bundle.read_bundle_file(POLY_MODEL_PATH)
        gen_map = polyphony_rnn_sequence_generator.get_generator_map()
        _poly_generator = gen_map["polyphony"](checkpoint=None, bundle=bundle)
        _poly_generator.initialize()

    _initialized = True


def _build_primer(notes, qpm):
    import magenta.music as mm
    seq = mm.NoteSequence()
    seq.tempos.add(qpm=qpm)
    t = 0.0
    step = 60.0 / qpm
    for pitch in notes:
        seq.notes.add(pitch=int(pitch), start_time=t, end_time=t + step, velocity=80)
        t += step
    seq.total_time = t
    return seq


def _build_options(primer, num_steps, temperature, qpm):
    from magenta.protobuf import generator_pb2
    options = generator_pb2.GeneratorOptions()
    options.args["temperature"].float_value = temperature
    step_duration = 60.0 / qpm / 4
    start = primer.total_time
    end = start + num_steps * step_duration
    options.generate_sections.add(start_time=start, end_time=end)
    return options


def _save_midi(sequence, prefix):
    import magenta.music as mm
    os.makedirs("./output/drafts", exist_ok=True)
    path = f"./output/drafts/{prefix}_{int(time.time())}.mid"
    mm.sequence_proto_to_midi_file(sequence, path)
    return path


def _extract_notes(sequence):
    return [
        {"pitch": n.pitch, "start_time": round(n.start_time, 4),
         "end_time": round(n.end_time, 4), "velocity": n.velocity}
        for n in sequence.notes
    ]


@app.post("/generate_melody")
def generate_melody(req: GenRequest):
    try:
        _init_generators()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model init failed: {e}")
    if _melody_generator is None:
        raise HTTPException(status_code=503, detail="Melody model not loaded")
    try:
        primer = _build_primer(req.primer_notes, req.qpm)
        options = _build_options(primer, req.num_steps, req.temperature, req.qpm)
        result = _melody_generator.generate(primer, options)
        path = _save_midi(result, "melody")
        notes = _extract_notes(result)
        return {"midi_path": str(path), "notes": notes, "duration_seconds": round(result.total_time, 2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Melody generation failed: {e}")


@app.post("/generate_polyphony")
def generate_polyphony(req: GenRequest):
    try:
        _init_generators()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model init failed: {e}")
    if _poly_generator is None:
        raise HTTPException(status_code=503, detail="Polyphony model not loaded")
    try:
        primer = _build_primer(req.primer_notes, req.qpm)
        options = _build_options(primer, req.num_steps, req.temperature, req.qpm)
        result = _poly_generator.generate(primer, options)
        path = _save_midi(result, "polyphony")
        notes = _extract_notes(result)
        return {"midi_path": str(path), "notes": notes, "duration_seconds": round(result.total_time, 2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Polyphony generation failed: {e}")


@app.get("/health")
def health():
    models = []
    if _melody_generator or os.path.exists(MELODY_MODEL_PATH):
        models.append("attention_rnn")
    if _poly_generator or os.path.exists(POLY_MODEL_PATH):
        models.append("polyphony_rnn")
    return {"status": "ok", "models": models, "initialized": _initialized}


@app.get("/models")
def list_models():
    return {
        "melody_model": MELODY_MODEL_PATH,
        "melody_exists": os.path.exists(MELODY_MODEL_PATH),
        "poly_model": POLY_MODEL_PATH,
        "poly_exists": os.path.exists(POLY_MODEL_PATH),
    }
