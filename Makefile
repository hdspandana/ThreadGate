.PHONY: gate test eval app eval-all clean

gate:            ## kill gate - run before building anything further
	python scripts/kill_gate.py

test:            ## test suite, no network and no key required
	python -m pytest

eval:            ## every system except the model (safe without a key)
	python eval/run_eval.py --systems rules_raw rules_norm offline compromised compromised_q

eval-all:        ## every system INCLUDING all four model-backed ones; needs GEMINI_API_KEY
	python eval/run_eval.py --require-gemini \
	  --systems rules_raw rules_norm offline \
	    gemini ai_only hybrid_no_scan hybrid_no_validation \
	    compromised compromised_q

app:             ## Streamlit demo
	streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port 8501

clean:
	rm -rf data/runs/* .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
