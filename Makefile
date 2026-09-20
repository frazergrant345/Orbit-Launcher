.PHONY: run dist rpm clean

run:
	python3 -m launcher.app

dist:
	rm -rf dist
	mkdir -p dist/launcher-0.2.5
	cp -r launcher packaging pyproject.toml README.md LICENSE dist/launcher-0.2.5/
	tar -C dist -czf dist/launcher-0.2.5.tar.gz launcher-0.2.5

rpm: dist
	mkdir -p ~/rpmbuild/SOURCES ~/rpmbuild/SPECS
	cp dist/launcher-0.2.5.tar.gz ~/rpmbuild/SOURCES/
	cp packaging/launcher.spec ~/rpmbuild/SPECS/
	rpmbuild -ba ~/rpmbuild/SPECS/launcher.spec

clean:
	rm -rf dist build *.egg-info
