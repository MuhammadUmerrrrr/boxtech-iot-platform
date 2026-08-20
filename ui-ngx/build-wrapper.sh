#!/bin/bash
yarn "$@" 2>&1 | tee build-output.log
exit ${PIPESTATUS[0]}
