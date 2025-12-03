project := "tsn-scenarios"

# Create an archive of this repository and documentation website to
# share with others that do not have access to github.jpl.nasa.gov.
archive:
    #!/bin/sh
    mkdir tmp
    git clone $(git remote get-url origin) tmp/repo
    just tmp/repo/docs/init
    just tmp/repo/docs/build
    mv tmp/repo/docs/build/site tmp/docs
    version=$(cd tmp/repo && git log -1 --format=format:%h-%cs)
    dirname={{project}}-$version
    cat >tmp/README.txt <<EOF
    This archive contains both the {{project}} Git repository and
    documentation website.

    To view the documentation website:

    1. Start a local web server.  E.g.,

       python3 -m http.server 8080 -d docs

    2. Then navigate to http://localhost:8080
    EOF
    rm -rf $dirname
    mv tmp $dirname
    tar czf $dirname.tar.gz $dirname
