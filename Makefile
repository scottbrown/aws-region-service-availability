.PHONY: build discover fetch normalize serve clean

build: discover fetch normalize

discover:
	bash scripts/discover.sh

fetch:
	bash scripts/fetch_and_extract.sh

normalize:
	python3 scripts/normalize_build.py

serve:
	python3 -m http.server -d site 8000

clean:
	rm -rf build
