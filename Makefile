# Shortcuts for macOS/Linux. On Windows, run the commands from README.md directly.
.PHONY: setup data erp api ui test eval eval-all

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

data:
	cd backend && .venv/bin/python -m scripts.generate_dataset

erp:
	cd backend && .venv/bin/uvicorn mock_erp.main:app --port 8001 --reload

api:
	cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload

ui:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/python -m pytest -q

eval:
	cd backend && .venv/bin/python -m eval.run_eval

eval-all:
	cd backend && .venv/bin/python -m eval.run_eval
	cd backend && .venv/bin/python -m eval.run_eval --set holdout
	cd backend && .venv/bin/python -m eval.run_eval --erp-fail-rate 0.3
