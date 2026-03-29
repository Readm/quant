#!/bin/bash
set -e
cd /mnt/c/Users/assas/WorkBuddy/20260328144441/dashboard
npm install @types/node --save-dev 2>&1
npm run build 2>&1
echo "BUILD_DONE:exit_code=$?"
