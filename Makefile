.PHONY: install test demo collect report
install:
	python -m pip install -e '.[dev,live]'
test:
	python -m pytest -q
demo:
	hengseng demo
collect:
	hengseng collect
report:
	hengseng run
