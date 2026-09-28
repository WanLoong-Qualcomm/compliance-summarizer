End Goal: An AI in the loop application which ingest an excel file that produces a high level HTML report/summary for RF tracsceiver measurement compliances.

Overall Application Flow
1. Takes in user inputs (exel file, main pivot, etc...)
2. Verify user inputs. If valid ? Proceed to 3 : Exit
3. Verify excel compliance sheet. If valid ?  Goto 5 : Goto 4
4. If irrecoverable ? Exit : (User approval to continue ? Request for optional explantion, Goto 5 : Exit)
5. For each measurement
    5.0.1.  Filter
    5.1.    Calculate main statistics of all pivots 
    5.2.    Calculate comparison statistic between main pivot and all other pivots
    5.3.    Compile low level statsitics to key statistics
    5.4.    For each aggregate
        5.4.0.1.    Filter
        5.4.1.      Calculate main statistics of all pivots
        5.4.2.      Calculate comparison statistic between main pivot and all other pivots
        5.4.3.      Compile low level statsitics to key statistics
    5.5. Compile aggregate-centric charts with key statistics
    5.6. Merge prompt, input/output templates and resources and generate the per-measurement report/summary via an AI client.
6. Merge prompt, overall input/output templates and AI per-measurement report/summary and generate the whole compliance report/summary.

v0.1 (Current Milestone)
1. Implement overall application flow, UI via a settings.json.
    - Only enabled for "SIGPATH" test.
    - Only "Gain" measurement.
    - No aggregation capabilities and aggregation-centric charts.
    - Model usage is bypassed (output of the model is the input of the model).
    - Current output will be an html file with all the compiled statsitics as well as with embedded graphics (is this possible?)
    - Prompt consturctions cen be ignored.

2. Information
    2.1. The excel file
        - Reference excel: "./EXMAPLE.xlsm", Sheet: "Combined"
        - Pivots will be on row 2 ("DUT-1_VAR1", "DUT-2_VAR1", "DUT-3_VAR2")
        - Pivot fields will be on row 3 ("MIN", "MAX", ...)
        - Column headers will be on row 4 ("LNAMODE", "CAMODE", ...)
            - Column headers within this excel sheet are considered compulsory.
    2.1.1. Coverage gaps
        - Within this excel sheet, there are blank pivot fields for both "VAR1" pivots when compared to "VAR2" pivot.
        - These are called coverage gaps, and should be conveyed to the user via step 3 of the application flow.
        - This information should be conveyed in a high-level manner (e.g. DUT-1_VAR1 has n coverage gaps, DUT-2_VAR1 has ...).
        - This is not a irrecoverable failure.
        - coverage gaps should be ignored when calculating main statistics for each individual pivot (e.g. ignore blank fields when calculating failure rates).
        - When calculating comparison statistics, how coverage gaps are ignored is dependent on the statistics (e.g. main pivot's degradation for the top 5 worst wcMargin fail cases is a left join between the two pivots *values should be NA instead of ommiting the whole row if there is a coverage gap in the secondary pivot only*, mean/max degradation/improvment is like an intersect between the two pivots *ommited from calculation if either value is not present*) <if it does not make sense, please rephrase it in a way that makes sense>.
    2.1.2. Measurement Main Statistics
        - Independent for each pivot.
        - Top 20 failure cases, show the compliance table as is, with main pivot's wcMargin sorted in asceinding order (most negative/smallest at the top) include Delta (Degradation/Improvment) between main pivot and other pivots as well *only for Measurement main Statistics*.
        - average degradation (degradation only) between main pivot and all other pivots for main pivot failure cases only.
        - failure rate, worst wcMargin for each pivot
        - Failure path (combination of all the cols) for the worst Failure (smallest wcMargin) of the main pivot.
    2.1.3. Measurement Comparison statstics
        - Degradation/Unchanged/Improvmement rate (after accounting for acceptable variation)
        - Max Degradatopm/Improvement
    2.1.4. Aggregation Statistics
        - Same as Measurement Main Statisitcs, excluding top 20 failure cases compliance table entirely and average degradation between ain pivot and all other pivots
    2.1.5. Aggregate Comparison statistics
        - Exact same as Measurement Comparison statistics.

    *NOTE*
    The "Result?" column should always never be used to determine pass/fail statistics/metric. Use the pivot's wcMargin field, if it is negative, it signifies a failure.
    Degradation should be calculatd with the "NN_25c AVG" field.

    2.2. settings.json
        - The current input file for v0.1


3. Implementation
    3.1. Implementation should follow standard coding best practices.
    3.2. Feel free to use any packages, such as pandas, dataframe images, plotly, np, etc...
    3.3. Please do not write complicated boilerplate validation or whatever code that is prone to breaking. if theres something out there which does what you want, use it
    <insert more details>




