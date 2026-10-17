# Contributing

Run the tests from the plugin root:

```
python3 -I -m unittest discover -s tests
```

- Python standard library only. No new dependencies.
- The engine makes no network calls and writes no files. Keep it that way.
- Rule ids: use an official PINT AE id (`ibr-...-ae`, `aligned-ibrp-...`) only when the check mirrors that Schematron rule. Otherwise use an `mc-` id.
- Add a test in `tests/test_check_uae.py` for every new check.
- Use made-up data in tests, samples and issues. Never real invoices.
