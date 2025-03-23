pipeline {
    agent any
    environment {
        DOCKER_REGISTRY = 'docker.sciencedataexperts.com'
        NAME = 'AMOS Server'
        IMAGE_NAME = 'amos-server'
        IMAGE_TAG = 'latest'
    }

    stages {
        stage('Setup Environment') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'jenkins', usernameVariable: 'USERNAME', passwordVariable: 'PASSWORD')]) {
                    sh "docker login -u $USERNAME -p $PASSWORD $DOCKER_REGISTRY"
                }
            }
        }

        stage('SCM') {
            steps {
                git poll: true, branch: 'dev', credentialsId: 'valery_tkachenko', url: 'https://bitbucket.org/scidataexperts/amos-server.git'
            }
        }

        stage('Dependencies check') {
            steps {
                dependencyCheck additionalArguments: "--nvdApiKey ${NVD_API_KEY}", odcInstallation: 'OWASP-Dependency-Check'
                dependencyCheckPublisher pattern: ''
            }
        }

        stage('Dockerize') {
            steps {
                sh "docker buildx use mybuilder"
                sh "docker buildx build --platform linux/amd64 --tag ${DOCKER_REGISTRY}/epa/${IMAGE_NAME}:${IMAGE_TAG} --push ."
            }
        }

        stage('Security Scan') {
            steps {
                sh "trivy image ${DOCKER_REGISTRY}/epa/${IMAGE_NAME}:${IMAGE_TAG}"
            }
        }

        stage('Deploy') {
            steps {
                withKubeConfig([credentialsId: 'k8s', serverUrl: 'https://k8s.sciencedataexperts.com:6443']) {
                    sh "kubectl rollout restart deployment ${IMAGE_NAME}"
                }
            }
        }
    }

    post {
        always {
            step([$class: 'Mailer', recipients: emailextrecipients([[$class: 'DevelopersRecipientProvider'], [$class: 'CulpritsRecipientProvider'], [$class: 'RequesterRecipientProvider']])])
        }
    }
}
