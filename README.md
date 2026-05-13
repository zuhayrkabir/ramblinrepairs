# Ramblin' Repairs

## Quick Notes for Team

Git Branch Workflow (PowerShell) — dev → feature → dev → main
==========================================================

Assumptions
-----------
- Remote repo is named: origin
- Main branch is: main
- Integration branch is: dev
- Feature branch example name: features/base-template
- You are running these commands INSIDE your repo folder (the one that contains .git)


A) Create a NEW feature branch UNDER dev
----------------------------------------
1) Switch to dev
git checkout dev

2) Update dev with the latest remote changes
git pull origin dev

3) Create and switch to your new feature branch from dev
git checkout -b features/base-template

4) Push the new branch to GitHub and set upstream tracking
git push -u origin features/base-template


B) Do work on the feature branch
---------------------------------------------------------
1) Confirm you are on the feature branch
git status

2) Stage + commit your changes
git add .
git commit -m "Update Message"

4) Push your feature branch
git push


C) Keep your feature branch up-to-date with dev (before merging)
---------------------------------------------------------------
This reduces merge surprises and moves conflicts onto your feature branch (where you can fix them).

1) Update local dev
git checkout dev
git pull origin dev

2) Merge dev into your feature branch
git checkout features/base-template
git merge dev

3) If there are conflicts:
   - Edit conflicted files and resolve the markers
   - Then:
git add .
git commit -m "Resolve merge conflicts from dev"

4) Push the updated feature branch
git push


D) Merge feature → dev (the “daisy chain” step 1)
--------------------------------------------------
- Base: dev
- Compare: features/base-template
- Merge

After merging the PR, sync your local dev:
git checkout dev
git pull origin dev


OR (all local commands):
1) Switch to dev and update it
git checkout dev
git pull origin dev

2) Merge the feature branch into dev
git merge features/base-template

3) Push dev to GitHub
git push origin dev


E) Merge dev → main (the “daisy chain” step 2)
-----------------------------------------------
Open a Pull Request on GitHub
- Base: main
- Compare: dev
- Merge

After merging the PR, sync your local main:
git checkout main
git pull origin main


OR (all local commands):
1) Switch to main and update it
git checkout main
git pull origin main

2) Merge dev into main
git merge dev

3) Push main to GitHub
git push origin main


F) Clean up: delete the feature branch (after it’s merged)
----------------------------------------------------------
1) Delete the remote branch (optional but recommended once merged)
git push origin --delete features/base-template

2) Delete the local branch
git branch -d features/base-template
