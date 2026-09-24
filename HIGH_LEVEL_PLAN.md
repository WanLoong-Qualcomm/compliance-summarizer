# High-Level Plan

## 1. Overview

This project aims to build a desktop application that produces an HTML summary/report of the compliance table generated from RF transceiver silicon testing. The report should be suitable for direct embedding in an email. The eventual user interface is still to be determined; it may be web-based or use another approach.

Report generation follows a fixed procedure with an AI model in the loop in the intended overall flow.

## 2. Terminology

The following terms establish the context for the plan:

- **AI**: Artificial intelligence. In the intended overall flow, an AI model helps generate and make the report content coherent. AI is bypassed in v0.1.
- **25C**: The 25-degree-Celsius test condition.
- **BC improvement**: Best-case improvement calculated from the delta between the pivot field of interest and another pivot field.
- **BBPATH**: Baseband path, identifying the baseband path used by the measurement.
- **BAND**: The operating frequency band associated with the measurement.
- **BW**: Bandwidth.
- **CAMODE**: Carrier Aggregation Mode, identifying the carrier-aggregation configuration.
- **Channel**: The channel or channel index associated with the measurement.
- **CHAR**: Characterization, the process of measuring and evaluating device or block behavior.
- **Compliance**: The pass/fail assessment of measured results against defined lower and upper limits.
- **DLP**: Downlink Pipe, identifying the downlink path or pipe used by the measurement.
- **DUT**: Device Under Test, the RF transceiver device being measured.
- **Excel workbook**: An `.xlsx` or `.xlsm` file containing the compliance data. An `.xlsm` file is an Excel workbook that may contain macros.
- **FREQ**: The frequency associated with a measurement.
- **F0_MHZ**: The F0 frequency value expressed in megahertz.
- **GAINMODE**: Automatic Gain Controller gain mode. Smaller values indicate higher gain.
- **GAIN**: The measured gain of the signal path.
- **HTML**: HyperText Markup Language, the format used for the generated summary/report.
- **IP2ACS**: Second-order intercept point for adjacent-channel selectivity.
- **IP2IB**: Second-order intercept point in band.
- **IP3ACS**: Third-order intercept point for adjacent-channel selectivity.
- **IP3IB**: Third-order intercept point in band.
- **LL / UL**: Lower Limit and Upper Limit, the compliance limits used to assess a result.
- **LNAMODE**: Low-Noise Amplifier Mode, identifying the LNA configuration.
- **MVP**: Minimum Viable Product, the smallest stage of the project used to test its viability.
- **MEASPORT**: Measurement port, identifying the port used for the measurement.
- **MIN / MAX**: The minimum and maximum measured values for a pivot field.
- **NN split**: The test split identified as NN. The source plan does not further expand the NN abbreviation.
- **NN_25C AVG**: The average measured value for the NN split at 25C.
- **PE**: Product Engineer, the engineer responsible for the relevant product-level analysis and reporting.
- **Pivot field**: A field used to group or compare compliance results across configurations or signal-path conditions.
- **Pivot statistic**: A statistic calculated for a pivot field, such as `MIN`, `MAX`, `NN_25C AVG`, or `wcMargin`.
- **PLL**: Phase-Locked Loop, a circuit used to generate or control a frequency reference. `DIV` represents its division factor.
- **RF**: Radio frequency.
- **RX**: Receiver, the receive portion of the RF transceiver.
- **JSON**: JavaScript Object Notation, the text format used for the v0.1 user settings.
- **RBW**: Resolution bandwidth, the bandwidth used for a measurement or residual-band assessment.
- **Result?**: The pass/fail result associated with a compliance case.
- **S11**: The input reflection coefficient measurement used to assess input matching.
- **SIGPATH**: Signal Path, the RX characterization test area in which basic characteristics along the signal path are measured.
- **SSNF**: Small-Signal Noise Figure, a measure of noise added by a device or signal path under small-signal conditions.
- **STD**: Standard, identifying the communications or operating standard associated with the measurement.
- **WC margin**: Worst-case margin. A negative `wcMargin` indicates a failure.
- **WC value**: The worst-case measured value associated with a pivot statistic. In the reference sheet, this is represented by `wcValue`.
- **Delta**: The calculated difference between corresponding values for the pivot field of interest and another pivot field.
- **Variation threshold**: The acceptable difference used to determine whether a delta represents degradation or improvement. Deltas at or below this threshold are treated as neither.
- **UI**: User interface. No UI is included in v0.1.

## 3. Overall Report-Generation Flow

1. The user provides the Excel file path, the relevant sheet name, the reporting specification, background information, and high-level information about the dataset.
2. The application performs preliminary checks, including requirements and data-validity checks. If abnormalities are detected, it prompts the user or terminates the process.
3. The application performs preliminary data processing.
4. The application compiles key metrics, visualizations, and other data summaries according to the user-provided specification.
5. The application uses an AI service provider, through a client interface, to provide the data and prompts needed to generate portions of the report.
6. The application combines the report portions and provides the complete report to the AI model so that it is coherent as a whole.
7. The application generates the final HTML summary/report.

## 4. Current Stage and Scope

The project is currently at the proof-of-concept and MVP stage. The purpose of this stage is to test the tool's viability and whether it improves the efficiency of the engineer's reporting workflow.

### v0.1 Scope

Version 0.1 focuses only on RX (receiver) SIGPATH (signal path) characterization bench-testing compliances.

The supported measurement is GAIN at 25C for the NN split. The initial implementation reports GAIN only. Gain-DNL is excluded from this version.

There is no user interface in v0.1. The application uses a `settings.json` file to collect the user's specifications. AI is also bypassed in this version so that the deterministic input and output can be evaluated first.

## 5. Background

The tool is intended to optimize the report and summary-writing portion of the workflow for an RX block PE (Product Engineer) performing SIGPATH characterization on RF transceiver DUTs (Devices Under Test).

### 5.1 SIGPATH Background

SIGPATH is a fundamental test of the RX block in which basic characteristics along a signal path are tested. The test areas covered by the broader SIGPATH context are:

1. **GAIN**
   - **Gain** - the primary gain measurement and the focus of v0.1.
   - **Gain-DNL** - gain differential nonlinearity, or the difference in gain between successive gain modes. This is not included in v0.1.
2. **SSNF (Small-Signal Noise Figure)**
   - **SSNFWSPURREMOVAL** - SSNF with spur removal.
   - **SSNF-LAST/FIRSTRBWSPURREMOVAL** - SSNF for the first/last residual bandwidth with spur removal.
3. **Linearities**
   - **GCIB** - Gain Compression In Band.
   - **IP2IB** - Second-Order Intercept Point In Band.
   - **IP2ACS** - IP2 Adjacent Channel Selectivity.
   - **IP3IB** - Third-Order Intercept Point In Band.
   - **IP3ACS**.
4. **S11**
   - **S11-LOW** - S11 lower-frequency marker.
   - **S11-MID**.
   - **S11-HIGH**.

### 5.2 Compliance Sheet Background

The compliance sheet reports pass/fail results for these tests across a signal path and configuration.

In the reference `Combined` sheet:

- Pivot-field labels appear in row 2.
- Pivot statistics appear in row 3.
- Signal-path and test-information column headers begin in row 4.

The compliance data must contain at least:

- One pivot field.
- The following pivot statistics: `MIN`, `MAX`, `NN_25C AVG`, and `wcMargin`.
- The following signal-path and test-information columns: `LNAMODE`, `CAMODE`, `STD`, `BAND`, `MEASPORT`, `DLP`, `DIV`, `TESTNAME`, `GAINMODE`, `BBPATH`, `FREQ`, `CHANNEL`, `Result?`, `LL`, and `UL`.

The reference sheet also contains additional fields and statistics, such as `BW`, `F0_MHZ`, and `wcValue`; these are not part of the minimum v0.1 requirement listed above.

Any change to the column headers may indicate a change in the signal path through the DUT.

## 6. v0.1 User Inputs and Operating Flow

### 6.1 User Inputs

The user starts the command-line application. The application creates a JSON file, instructs the user to complete it, and waits for the user to press Enter before continuing.

The JSON input includes:

- Excel file path (`.xlsx` or `.xlsm`).
- Compliance sheet name.
- List of tests to report. GAIN is the default and only supported test in v0.1.
- Acceptable variation for each test, used later to calculate delta statistics. The default variation for GAIN is `0.2`.
- Background information for later prompting.
- Pivot field of interest.
- Whether to bypass the model. This defaults to `True` in v0.1.

### 6.2 Application Verification

The application verifies the selected compliance sheet by checking that the required columns and pivot statistics are present.

It then:

1. Determines how many pivot fields are available.
2. Verifies that the selected pivot field of interest is present.
3. Requests background information from the user for each pivot field through the command line.
4. Checks the `MIN` statistic for GAIN whenever GAIN is present, even if it was not explicitly selected. A negative GAIN value can indicate a poor or disconnected port.
5. Displays any negative GAIN values in a table similar to the compliance table and asks the user whether to proceed.

The application proceeds when the checks are satisfactory and any user decision required by the checks has been provided.

## 7. v0.1 Data Processing and Compilation

The application filters the data by `TESTNAME`; in v0.1, this means processing GAIN only. The purpose of this processing is to summarize the data and avoid sending unnecessary volume to the AI model in a later version.

When a case is retained for analysis, the relevant signal-path parameters that caused the case are retained as well, for example in a table or equivalent summary.

### 7.1 Comparative Metrics

For the selected pivot field of interest, the application:

- Calculates the delta between each `NN_25C AVG` and the corresponding value for every other pivot field. This produces one additional delta value for each comparison.
- Calculates the failure rate for each pivot field, expressed as failures divided by total cases.

### 7.2 Failure-Case Analysis

For cases where `Result? = FAIL`, the application:

- Sorts the cases by the pivot field of interest's worst, or most negative, `wcMargin`.
- Retains the top 50 cases in this order so that they can be included in a screenshot and always included in the report.
- Retains the five worst cases for closer analysis.
- For the worst cases for the pivot field of interest, compares the `wcMargin` values of the other pivot fields to determine whether they degrade or improve.
- Keeps the `wcMargin` values for all other pivot fields in context.
- Tracks WC degradation and BC improvement for the calculated deltas.
- Checks for degradation-led failures, such as cases where the pivot field of interest has more failures than the comparison fields, and retains those cases for consideration.

### 7.3 Pass-Case Analysis

For cases where `Result? = PASS`, the application:

- Sorts cases by the smallest positive `wcMargin` for the pivot field of interest.
- Retains the five closest-to-failure pass cases.
- Checks those cases for degradation. If the margins remain acceptable, the degradation may be ignored; for example, a margin of `0.4 dB` may remain acceptable.

### 7.4 Overall Comparison

Across pass and fail cases, the application:

- Calculates degradation and improvement rates between the pivot field of interest and the other pivot fields.
- Applies the user-provided variation threshold. Deltas at or below the threshold are not treated as either degradation or improvement.
- Calculates the maximum degradation and maximum improvement.

## 8. v0.1 Output

AI generation is bypassed for v0.1. A dummy or stub may stand in for the model step while the deterministic processing is validated.

The application compiles the user inputs, analysis results, and visualizations into a fixed HTML report. User inputs appear at the top, followed by the compiled data analysis and graphics. The report is used to check the input and output of the v0.1 processing flow.
