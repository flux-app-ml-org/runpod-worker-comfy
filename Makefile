.PHONY: test test-unit test-integration

test: test-unit test-integration

test-unit:
	python -m unittest discover

test-integration:
	cd tests/integration && ./run_docker_tests.sh 
