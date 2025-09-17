---
eng.ms.tsg.expiryDate: 8/31/2021
eng.ms.tsg.applicableTo: All
eng.ms.tsg.requireJIT: Yes
eng.ms.tsg.owningTeam: PROJECTVIENNASERVICES\Pipelines

uid: how-to-use-easydri-query-for-pipeline-run-failures
title: How to use EasyDRI query for Pipeline run failures
---

# How to use EasyDRI query for Pipeline run failures

## Overview

EasyDRI Kusto queries can provide a quick reference to support investigation of a failed pipeline run. If you fill in FailedRunId field when you file new IcM ticket against "Project Vienna Services/AEther" team, it'll be automatically enriched by EasyDRI IcM handler which internally uses EasyDRI Kusto queries and its failure classification rules. You may also manually run these EasyDRI Kusto functions with Azure Data Explorer or Kusto Explorer client application.

## Solution

How to use queries

Connect to Viennause2 Kusto cluster <https://dataexplorer.azure.com/clusters/viennause2/databases/Vienna>

Run the following query with failed run pipeline or pipeline step run ID first:

``` k
EasyDRI_GetQueryTimeWindow('3c20fe3f-0fc6-44cb-9b5c-73de88a6525e')
```

And then run the following query with the start and end time from the above query to get target cluster name:

``` k
EasyDRI_GetClusterName('2021-08-16T18:45:39Z', '2021-08-16T23:04:34Z','3c20fe3f-0fc6-44cb-9b5c-73de88a6525e')
```

And finally you can get failure classification information with start/end time and cluster name from the above step:

``` k
EasyDRI_GetFailureClassification('2021-08-16T18:45:39Z', '2021-08-16T23:04:34Z', 'viennaeun.northeurope', '2a87746f-ad42-4668-aaa7-46cf00a3c3f4')
| where failureName <> "Success"
```
