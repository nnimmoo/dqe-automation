# Pytest Introduction

I ran pytest commands in **tests** folder. Where the reports get created.

## Commands

```
# to run everything
pytest 
# to run marked tests
pytest unmarked
# to run tests with "validate_csv and not xfail" marks
pytest -m "validate_csv and not xfail"
```