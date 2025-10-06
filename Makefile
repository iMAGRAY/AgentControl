SHELL := /usr/bin/env bash
MAKEFLAGS += --no-builtin-rules --warn-undefined-variables
.DEFAULT_GOAL := status

SDK_RUNNER := ./scripts

.PHONY: init dev verify fix review ship doctor status

init:
	"${SDK_RUNNER}/init.sh"

dev:
	"${SDK_RUNNER}/dev.sh"

verify:
	"${SDK_RUNNER}/verify.sh"

fix:
	"${SDK_RUNNER}/fix.sh"

review:
	"${SDK_RUNNER}/review.sh"

ship:
	"${SDK_RUNNER}/ship.sh"

doctor:
	"${SDK_RUNNER}/doctor.sh"

status:
	"${SDK_RUNNER}/status.sh"
