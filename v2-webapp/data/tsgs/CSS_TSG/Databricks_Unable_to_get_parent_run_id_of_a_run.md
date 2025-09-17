---
eng.ms.tsg.expiryDate: 8/31/2021
eng.ms.tsg.applicableTo: All
eng.ms.tsg.requireJIT: Yes
eng.ms.tsg.owningTeam: PROJECTVIENNASERVICES\Pipelines

uid: databricks-unable-to-get-parent-run-id
title: Databricks - unable to get parent runId
---
# Databricks - unable to get parent runId

## Overview

Users are used to being able to use `Run.get_context()` to retrieve the `parent_run_id`
for a given `run_id`. In DatabricksStep, however, a little more work is required to achieve this.

## Solution

The solution is to parse the script arguments and set corresponding environment
variables to access the run context from within Databricks.
Note that this code may be provided to the user and should be run by the user.

Here is a code sample

``` python

from azureml.core import Run
import argparse
import os


def populate_environ():
    parser = argparse.ArgumentParser(description='Process arguments passed to script')
    parser.add_argument('--AZUREML_SCRIPT_DIRECTORY_NAME')
    parser.add_argument('--AZUREML_RUN_TOKEN')
    parser.add_argument('--AZUREML_RUN_TOKEN_EXPIRY')
    parser.add_argument('--AZUREML_RUN_ID')
    parser.add_argument('--AZUREML_ARM_SUBSCRIPTION')
    parser.add_argument('--AZUREML_ARM_RESOURCEGROUP')
    parser.add_argument('--AZUREML_ARM_WORKSPACE_NAME')
    parser.add_argument('--AZUREML_ARM_PROJECT_NAME')
    parser.add_argument('--AZUREML_SERVICE_ENDPOINT')

    args = parser.parse_args()
    os.environ['AZUREML_SCRIPT_DIRECTORY_NAME'] = args.AZUREML_SCRIPT_DIRECTORY_NAME
    os.environ['AZUREML_RUN_TOKEN'] = args.AZUREML_RUN_TOKEN
    os.environ['AZUREML_RUN_TOKEN_EXPIRY'] = args.AZUREML_RUN_TOKEN_EXPIRY
    os.environ['AZUREML_RUN_ID'] = args.AZUREML_RUN_ID
    os.environ['AZUREML_ARM_SUBSCRIPTION'] = args.AZUREML_ARM_SUBSCRIPTION
    os.environ['AZUREML_ARM_RESOURCEGROUP'] = args.AZUREML_ARM_RESOURCEGROUP
    os.environ['AZUREML_ARM_WORKSPACE_NAME'] = args.AZUREML_ARM_WORKSPACE_NAME
    os.environ['AZUREML_ARM_PROJECT_NAME'] = args.AZUREML_ARM_PROJECT_NAME
    os.environ['AZUREML_SERVICE_ENDPOINT'] = args.AZUREML_SERVICE_ENDPOINT

populate_environ()
run = Run.get_context(allow_offline=False)
print(run._run_dto["parent_run_id"])
```
