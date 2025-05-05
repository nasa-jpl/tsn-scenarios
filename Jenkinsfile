#!/usr/bin/env groovy

pipeline {
    agent any
    stages {
        stage('Docs') {
            when { changeset "docs/**" }
            steps {
                build '/hpsc/lab/antora/main'
            }
        }
    }
}
