---
eng.ms.tsg.expiryDate: 8/31/2021
eng.ms.tsg.applicableTo: All
eng.ms.tsg.requireJIT: Yes
eng.ms.tsg.owningTeam: PROJECTVIENNASERVICES\Pipelines

uid: what-to-check-if-es-runId-is-not-found
title: What to check if Execution Service runId is not found
---

# What to check of Execution Service runId is not found

## Overview

If RunId cannot be found in CosmosDb then this could be caused by workspace being deleted

## Solution

Run the following Kusto query to find if the workspace was deleted

```kusto
UnionOfAllLogs("Vienna", "traces")
| where PreciseTimeStamp > ago(2d)
| where Environment == "eastus2"
| where app contains "execution"
| where message contains [Workspace] and message contains "Handling WorkspaceStatusChangedEvent for workspaceId"
| project PreciseTimeStamp, message, operation_Id, Environment
| order by PreciseTimeStamp desc
```
