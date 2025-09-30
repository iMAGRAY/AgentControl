.PHONY: help setup lock init dev verify review doctor fix ship roadmap status task tasks select conflicts comment list summary grab assign release complete validate history add take drop done task-add task-take task-drop task-done task-history sync-roadmap architecture-sync arch-edit arch-apply agent-cycle progress

help:
	@echo "Доступные цели: setup lock init dev verify fix ship roadmap status task <subcommand> task-add task-take task-drop task-done task-history"

DEV_ENV=LC_ALL=C.UTF-8

scripts_dir := ./scripts

execute = $(DEV_ENV) $(scripts_dir)/$1.sh
execute_task = $(DEV_ENV) $(scripts_dir)/task.sh $1 $(TASK_ARGS)

setup:
	@$(call execute,setup)

lock:
	@$(call execute,update-lock)

init:
	@$(call execute,init)

dev:
	@$(call execute,dev)

verify:
	@$(call execute,verify)

review:
	@$(call execute,review)

doctor:
	@$(call execute,doctor)

fix:
	@$(call execute,fix)

ship:
	@$(call execute,ship)

roadmap:
	@$(call execute,sync-roadmap)
	@$(call execute,roadmap-status)

architecture-sync:
	@$(call execute,sync-architecture)

arch-edit:
	@$(DEV_ENV) $(scripts_dir)/arch.sh edit

arch-apply:
	@$(DEV_ENV) $(scripts_dir)/arch.sh apply

agent-cycle:
	@$(call execute,agent-cycle)

progress:
	@$(DEV_ENV) python3 $(scripts_dir)/progress.py

ifeq ($(firstword $(MAKECMDGOALS)),task)
TASK_SUBCOMMAND := $(word 2,$(MAKECMDGOALS))
TASK_ARGS := $(wordlist 3,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
status select conflicts comment list summary grab assign release complete validate history add take drop done:
	@:
else ifeq ($(firstword $(MAKECMDGOALS)),tasks)
TASK_SUBCOMMAND := $(word 2,$(MAKECMDGOALS))
TASK_ARGS := $(wordlist 3,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
status select conflicts comment list summary grab assign release complete validate history add take drop done:
	@:
else
status:
	@$(call execute,status)
endif

task:
	@$(call execute_task,$(if $(TASK_SUBCOMMAND),$(TASK_SUBCOMMAND),list))

tasks: task
	@:

task-add:
	@$(call execute_task,add)

task-take:
	@$(call execute_task,take)

task-drop:
	@$(call execute_task,drop)

task-done:
	@$(call execute_task,done)

task-history:
	@$(call execute_task,history)
