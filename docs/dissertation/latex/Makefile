.PHONY: pdf clean

MAIN := main.tex
OUT := build

pdf:
	@mkdir -p $(OUT)
	@if command -v latexmk >/dev/null 2>&1; then \
		TEXINPUTS="vendor//:$${TEXINPUTS}" latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(OUT) $(MAIN); \
	elif command -v tectonic >/dev/null 2>&1; then \
		TEXINPUTS="vendor//:$${TEXINPUTS}" tectonic $(MAIN) --outdir $(OUT) --keep-logs; \
	else \
		echo "Install latexmk (TeX Live/MacTeX) or tectonic, then rerun 'make pdf'."; \
		exit 1; \
	fi

clean:
	@if command -v latexmk >/dev/null 2>&1; then latexmk -C -outdir=$(OUT) $(MAIN); fi
	@rm -rf $(OUT)

