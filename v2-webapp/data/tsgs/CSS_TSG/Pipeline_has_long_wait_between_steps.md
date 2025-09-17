---
eng.ms.tsg.expiryDate: 8/31/2021
eng.ms.tsg.applicableTo: All
eng.ms.tsg.requireJIT: Yes
eng.ms.tsg.owningTeam: PROJECTVIENNASERVICES\Pipelines

uid: pipeline-has-long-wait-between-steps
title: Pipeline has long wait between steps
---

# Pipeline has long wait between steps

## Overview

Users may experience long wait times between steps. In one instance, this was due to a bug in the
SDK, but you can check for other obvious issues with the steps below when a user reports delays
between steps.

## Solution

How to debug the issue

Check the following Kusto query to find the errors for jobs with a long delay between
CreateOperation and JobRunning:

``` k
cluster("viennatest").database("Vienna").JobEvent
| where WorkspaceName == "<workspacename>" and SubscriptionId == "<subscription>"
| join kind=inner (cluster("viennatest").database("Vienna").JobEvent
    | where WorkspaceName == "<workspacename>" and SubscriptionId == "<subscription>"and env_time > now()-15d
    | where EventType == "CreateOperationAccepted"
    | project env_time, JobName, JobGuid, EventType
    | join (cluster("viennatest").database("Vienna").JobEvent
        | where WorkspaceName == "<workspacename>" and SubscriptionId == "<subscription>"and env_time > now()-15d
        | where EventType == "JobRunning"
        | project env_time, JobName, JobGuid, EventType) on JobGuid
    | extend duration = env_time1 - env_time
    | sort by duration desc
    | take 20
    ) on JobName
| order by JobName, env_time asc
| project EventType, env_time, ResultCode, ExecutionState, StartTime, JobQueueingCode, JobQueueingMessage, JobName

```

This will potentially return useful hints such as
`"Run requested 1 node(s), but 'cpupool' cluster has 20 busy node(s) and 0 unusable nodes
out of 20 (max size)."`
In that case, look at the run logs and see why the other runs on the compute are taking so long.
Other things to check would be to look at the workspace runs, find runs already on the cpupool compute
and look at logs to see why they are stuck/slow.
