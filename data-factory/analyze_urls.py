#!/usr/bin/env python
"""
Analyze URLs found in GitHub Actions logs to understand which domains 
are causing false positives.
"""

import re
from collections import Counter

# Sample URLs from GitHub Actions logs (based on common patterns)
sample_log = """
Run actions/checkout@v4
https://github.com/actions/setup-node
https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz
https://objects.githubusercontent.com/github-production-release-asset-2e65be
https://api.github.com/repos/actions/setup-node
npm http fetch GET 200 https://registry.npmjs.org/express 45ms
https://api.nuget.org/v3/index.json
https://www.nuget.org/api/v2/package/Newtonsoft.Json/13.0.1
fetch https://registry.yarnpkg.com/@types/node/-/node-18.0.0.tgz
downloading https://files.pythonhosted.org/packages/source/p/pytest/pytest-7.4.0.tar.gz
GET https://crates.io/api/v1/crates/serde/1.0.0/download
pulled docker.io/library/node:18-alpine
https://ghcr.io/containers/podman:latest
https://mcr.microsoft.com/dotnet/sdk:8.0
https://cdn.jsdelivr.net/npm/jquery@3.7.0/dist/jquery.min.js
https://storage.googleapis.com/kubernetes-release/release/v1.28.0/bin/linux/amd64/kubectl
https://nodejs.org/dist/v18.17.0/node-v18.17.0-linux-x64.tar.xz
"""

URL_PATTERN = re.compile(r'https?://([^\s<>"\']+)', re.IGNORECASE)

TRUSTED_DOMAINS = {
    # GitHub
    'github.com', 'githubusercontent.com', 'github.io', 'githubassets.com',
    'pipelines.actions.githubusercontent.com',
    'actions-results.githubusercontent.com',
    'objects.githubusercontent.com',
    'codeload.github.com',
    # Package registries
    'npmjs.org', 'npmjs.com', 'registry.npmjs.org', 'npm.pkg.github.com',
    'yarnpkg.com', 'registry.yarnpkg.com',
    'pypi.org', 'files.pythonhosted.org', 'pypi.python.org',
    'maven.org', 'mavencentral.org', 'jfrog.io', 'repo1.maven.org', 'search.maven.org',
    'gradle.org', 'plugins.gradle.org', 'services.gradle.org',
    'rubygems.org', 'bundler.io',
    'crates.io', 'static.rust-lang.org', 'static.crates.io',
    'nuget.org', 'api.nuget.org',
    'packagist.org',
    'pkg.go.dev', 'proxy.golang.org', 'sum.golang.org', 'gopkg.in',
    # Container registries
    'docker.io', 'docker.com', 'registry.hub.docker.com', 'hub.docker.com',
    'gcr.io', 'ghcr.io', 'quay.io', 'mcr.microsoft.com',
    'index.docker.io', 'auth.docker.io', 'production.cloudflare.docker.com',
    # Cloud providers
    'amazonaws.com', 's3.amazonaws.com', 'cloudfront.net',
    'googleapis.com', 'google.com', 'gstatic.com', 'storage.googleapis.com',
    'microsoft.com', 'azure.com', 'visualstudio.com', 'azureedge.net',
    'blob.core.windows.net', 'windowsupdate.com',
    # CDNs
    'cloudflare.com', 'cloudflare-ipfs.com', 
    'fastly.net', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'unpkg.com',
    'bootstrapcdn.com', 'fontawesome.com',
    # CI/CD and dev tools
    'circleci.com', 'travis-ci.org', 'travis-ci.com',
    'sonarcloud.io', 'sonarqube.org', 'sonar.io',
    'codecov.io', 'coveralls.io', 'codeclimate.com',
    'shields.io', 'img.shields.io', 'badge.fury.io',
    'sentry.io', 'datadog.com', 'newrelic.com',
    # Common tools
    'nodejs.org', 'python.org', 'ruby-lang.org', 'java.com', 'oracle.com',
    'ubuntu.com', 'debian.org', 'alpine-linux.org', 'archlinux.org',
    'kernel.org', 'gnu.org', 'sourceforge.net',
    # Local
    'localhost', '127.0.0.1', '0.0.0.0',
}

def analyze_urls(log_text):
    all_urls = URL_PATTERN.findall(log_text)
    trusted = []
    untrusted = []
    
    for url in all_urls:
        domain = url.split('/')[0].lower()
        domain = domain.split(':')[0]
        
        is_trusted = any(domain.endswith(t) for t in TRUSTED_DOMAINS)
        
        if is_trusted:
            trusted.append((url, domain))
        else:
            untrusted.append((url, domain))
    
    return trusted, untrusted

if __name__ == "__main__":
    trusted, untrusted = analyze_urls(sample_log)
    
    print("=== TRUSTED URLs ===")
    for url, domain in trusted:
        print(f"  {domain}: {url[:60]}...")
    
    print(f"\n=== UNTRUSTED URLs ({len(untrusted)}) ===")
    for url, domain in untrusted:
        print(f"  {domain}: {url[:60]}...")
    
    # Count domains
    untrusted_domains = Counter(d for _, d in untrusted)
    print(f"\n=== Top Untrusted Domains ===")
    for domain, count in untrusted_domains.most_common(10):
        print(f"  {domain}: {count}")
