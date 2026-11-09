This folder sends your forward curves to Slope, TVFI's pricing model, and brings the results back
for you to analyse.

Before you start, install Python 3.9 or later, then run `pip install requests openpyxl` once.

## What each file is for

| File | What it is for |
|---|---|
| `run_curves.py` | You add to this. It sends each of your curves to Slope. |
| `analyse_results.py` | You add to this. It collects the results and does your analysis. |
| `slope_api.py` | The Slope library. Do not change it. |
| `sample_curve.xlsx` | An example curve file, to copy and edit. |

## Writing your scripts

### Curve files

Each curve is its own Excel file with one sheet, named `Sheet1`, and two columns:

| Policy Duration | Forward Rate |
| --- |   ---  |
|  1  | 0.0326 |
| ... |   ...  |
| 100 | 0.0412 |

- Policy Duration always runs from 1 to 100.
- Forward Rate is the one-year interest rate for that year: duration 1 is the first year, duration 2
  the second, and so on.
- Write rates as annual decimals: 5.23% is `0.0523`.

The easiest way to make one is to copy `sample_curve.xlsx` and change the rates. If a file is not
in this format, it will not be sent to Slope, and you will receive an informative error message.

The file name is the curve's name. `curve_a.xlsx` shows up in your results as `curve_a`. Each name can
be sent only once, so if you change a curve, save it under a new name.

### Functions you should use

`slope_api.py` gives you three functions. You do not need anything else in it.

**`run_slope_curve(curve_file, group)`** sends one curve to Slope. Call it once for each curve, in
`run_curves.py`:

```python
run_slope_curve("curve_a.xlsx", GROUP)
run_slope_curve("curve_b.xlsx", GROUP)
```

The work is split between two scripts. `run_curves.py` sends your curves and stops without
waiting for them. `analyse_results.py` waits for the runs to finish and downloads the results.

**`wait_for_runs()`** waits until all your runs have finished and tells you how each one went.
Use this in `analyse_results.py`:

```python
statuses = wait_for_runs()     # {"curve_a": "Completed", "curve_b": "Failed"}
```

**`load_results()`** gives you the results of every run that worked. For each curve you get seven
reports as CSV files (Cash Flows, Liabilities, LICAT and so on), which you open like any other CSV:

```python
results = load_results()
results["curve_a"]["Cash Flows"]   # the Cash Flows CSV of the curve in curve_a.xlsx
```

### Things to watch

- Only a run marked `Completed` worked.
- Keep your curve files inside this folder.
- Set `GROUP` in `run_curves.py` to your group number.
- Put all your code in `run_curves.py` and `analyse_results.py`. Your scripts cannot import code
  from your own other `.py` files, because we will not have those files when we run them.
  Libraries you install, such as pandas, are fine.

## Checking your work

Run your two scripts, one after the other:

```
python run_curves.py
python analyse_results.py
```

Nothing is sent to Slope. Your code gets results in the same layout as the real ones, but filled
with random numbers. If both scripts run from start to finish without errors, your code is ready.
The numbers themselves mean nothing yet.

As you run the scripts, three things appear in the folder:

- `runs.csv` lists every curve you have sent. If you run `run_curves.py` again, curves already on
  the list are skipped.
- `exports/` holds the reports.
- `dry_run_state.json` remembers which names you have used.

To start again from nothing, delete all three.

## Checkpoints

Before you send anything, make sure both scripts run from start to finish without errors (see
"Checking your work"). Then send us `run_curves.py`, `analyse_results.py` and your curve files.

We will run both of your scripts on Slope, one after the other, just as you did when checking
your work. Then we send the folder back to you, with the real reports and everything your
analysis produced.

If you change your analysis afterwards, you can run `python analyse_results.py` again yourself. It
will use the reports already in the folder.
