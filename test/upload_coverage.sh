#!/bin/bash

SHA=$(git rev-parse devel)
codecov --sha "$SHA" --slug "Coverage"
