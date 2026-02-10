#!/bin/bash
set -e

echo "Starting Prefect worker..."
prefect worker start --pool default-pool