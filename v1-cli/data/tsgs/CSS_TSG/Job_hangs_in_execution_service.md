---
eng.ms.tsg.expiryDate: 8/31/2021
eng.ms.tsg.applicableTo: All
eng.ms.tsg.requireJIT: Yes
eng.ms.tsg.owningTeam: PROJECTVIENNASERVICES\Pipelines

uid: job-hangs-in-execution-service
title: Job hangs in Execution Service
---

# Job hangs in Execution Service

## Overview

Users may experience jobs being stuck in various places. One of those is in Execution Service, when
a transient issue causes the Azure Storage SDK call to the AzureBlob to hang.
This TSG explains how to confirm whether this is the case when a user reports delay (note that
 the delay here is something that the user us experiencing, thus could be different and between different users).

## Solution

Check that the issue is not due to upstream causes:

0. Ask the clients for the logs.
1. Image building might have failed. In `20_image_build_log.txt` file, look for phrase
"Successfully built" followed by id towards the end of file.
2. Confirm also that the image was successfully pushed in logs immediately after.
3. Try the following Kusto query:

``` k

cluster("viennausee").database("Vienna").UnionOfAllLogs("Vienna", "requests")
| where Environment == "<environment>"                                        //example: 'southcentralus'
| where timestamp > datetime(<datetime>) and TIMESTAMP < datetime(<datetime>) //example: 2019-10-01 00:20:00.0000000
| where customDimensions.KubernetesApp contains "execution"
| where name contains "Execution/Start"
| where toint(resultCode) > 499
| where url contains "<runId>"                                                //example: '18faf71c-0b15-46ce-a43c-780ac2b155dc'
| project timestamp, name, operation_Id, resultCode, url

```

If you see multiple instances with the same `operation_Id`, and there's a large gap between two of
the timestamps, please add this case to the following [Task](https://dev.azure.com/msdata/Vienna/_workitems/edit/520072/?triage=true)
