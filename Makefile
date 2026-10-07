# Every target is `python -m <module>` rather than a console script, so it works
# from a Windows venv where Scripts/ is not on PATH. `make` itself is not
# installed on Windows by default: the same commands are written out in
# README.md and docs/TESTED_ENVIRONMENT.md for anyone without it.
.PHONY: gate test eval app eval-all secret-scan clean

PYTHON ?= python

gate:            ## kill gate - run before building anything further
	$(PYTHON) scripts/kill_gate.py

test:            ## test suite, no network and no key required
	$(PYTHON) -m pytest

eval:            ## every system except the model (safe without a key)
	$(PYTHON) eval/run_eval.py --systems rules_raw rules_norm offline compromised compromised_q

eval-all:        ## every system INCLUDING all four model-backed ones; needs GEMINI_API_KEY
	$(PYTHON) eval/run_eval.py --require-gemini \
	  --systems rules_raw rules_norm offline \
	    gemini ai_only hybrid_no_scan hybrid_no_validation \
	    compromised compromised_q

secret-scan:     ## credential scan, tree and git history (exit 1 on a hit)
	$(PYTHON) scripts/secret_scan.py

app:             ## Streamlit demo
	$(PYTHON) scripts/serve.py

clean:           ## remove caches and scratch run output (portable; no rm/find)
	$(PYTHON) scripts/clean.py
