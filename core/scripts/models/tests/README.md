# Test suites

The default publication test suite is self-contained:

```bash
python -m unittest discover -s core/scripts/models/tests -p 'test_*.py' -q
```

Files named `external_*.py` are retained integration tests for superseded
evidence pipelines. They require the historical evidence archive, which is
deliberately excluded from the publication repository. After materialising
that archive at its documented repository-relative paths, run them with:

```bash
python -m unittest discover -s core/scripts/models/tests -p 'external_*.py' -q
```

An external-evidence failure caused only by an absent historical fixture is
not a failure of the self-contained release suite. Code or assertion failures
after the fixtures are supplied must still be investigated.
