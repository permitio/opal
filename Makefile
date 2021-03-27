.PHONY: help

.DEFAULT_GOAL := help

clean:
	rm -rf *.egg-info build/ dist/

publish-common:
	$(MAKE) clean
	python setup/setup_common.py sdist bdist_wheel
	python -m twine upload dist/*

publish-client:
	$(MAKE) clean
	python setup/setup_client.py sdist bdist_wheel
	python -m twine upload dist/*

publish-server:
	$(MAKE) clean
	python setup/setup_server.py sdist bdist_wheel
	python -m twine upload dist/*

publish:
	$(MAKE) publish-common
	$(MAKE) publish-client
	$(MAKE) publish-server
