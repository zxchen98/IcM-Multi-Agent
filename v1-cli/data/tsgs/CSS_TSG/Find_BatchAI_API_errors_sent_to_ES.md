---
eng.ms.tsg.expiryDate: 8/31/2021
eng.ms.tsg.applicableTo: All
eng.ms.tsg.requireJIT: Yes
eng.ms.tsg.owningTeam: PROJECTVIENNASERVICES\Pipelines

uid: find-batchai-api-errors-sent-to-es
title: Find Batch-AI API errors sent to Execution Service
---

# Find Batch-AI API errors sent to Execution Service

## Overview

The run may fail during Compute phase (you can see in the logs that the job started to run on the compute and then failed).
In that case, Execution service receives the error(s) from BatchAI.
ES does not log the exact output from BatchAI API, and in some cases you might need to have an
understanding of what has been sent.

## Solution

Connect to BatchAI Kusto cluster <https://azurebatchai.kusto.windows.net>
(for air gapped regions, the cluster's name should remain the same).

Run the following Kusto query to find the Batch API errors for a run

``` k
cluster("Azurebatchai").database("azurebatchaiprod").JobEvent
| where JobName =~ "Turingv2_Thread_Preprocess_1599961010252"
| distinct  JobErrorCategory, JobErrorMessage, JobErrorDetails, JobErrors

```

The errors and error messages are separated by comma
