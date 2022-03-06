#!/bin/bash

# Try this after running API with "sam-beta-cdk local start-api".
# See: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-cdk-testing.html

response=`curl -sS --location --request POST 'https://qs4fnqf0ra.execute-api.ap-northeast-2.amazonaws.com/prod/trigger' \
--header 'Content-Type: application/json' \
--data @<(cat <<EOF
{
  "codepipelineName": "fip-pipeline-orchest"
}
EOF
)`
echo "[Response]: $response"


## FEP Decrypt.
#plaintext=`curl -sS --location --request POST 'http://localhost:3000/decrypt' \
#--header 'Content-Type: application/json' \
#--data @<(cat <<EOF
#{
#  "input": "$ciphertext",
#  "radix": 10
#}
#EOF
#) | jq -r '.plaintext'`
#echo "[FPE Decrypt]: $ciphertext => $plaintext"
#
#
## Envelope Encrypt.
#original='1234567890123456'
#ciphertext=`curl -sS --location --request POST 'http://localhost:3000/envelope-encrypt' \
#--header 'Content-Type: application/json' \
#--data @<(cat <<EOF
#{
#  "input": "$original"
#}
#EOF
#) | jq -r '.ciphertext'`
#echo "[Envelope Encrypt]: $original => $ciphertext"
#
#
## Envelope Decrypt.
#plaintext=`curl -sS --location --request POST 'http://localhost:3000/envelope-decrypt' \
#--header 'Content-Type: application/json' \
#--data @<(cat <<EOF
#{
#  "input": "$ciphertext"
#}
#EOF
#) | jq -r '.plaintext'`
#echo "[Envelope Decrypt]: $ciphertext => $plaintext"
