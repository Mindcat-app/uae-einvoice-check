# Contributing

Run the tests from the plugin root:

```
python3 -I -m unittest discover -s tests
```

- Keep `engine/check_uae.py` on the Python standard library, with no network code.
- Give each new check the official PINT AE rule id when one exists, or an `mc-` id when it does not, and add a test.
- Use made-up data only in issues, tests and samples. Never paste real invoices, TRNs or customer names.
