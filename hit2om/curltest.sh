#!/usr/bin/env bash

BASEURL=https://${CTLIP:?}/ConfigurationManager/

# These do not need authorization:
curl -k -H "Accept:application/json" -H "Content-Type:application/json" $BASEURL/configuration/version
curl -k -H "Accept:application/json" -H "Content-Type:application/json" $BASEURL/v1/objects/storages

echo "Logging in with maintenance..."
json=$(curl -k -H "Accept:application/json" -H "Content-Type:application/json" -u maintenance:raid-maintenance -X POST $BASEURL/v1/objects/sessions/ -d "")
echo $json
token=$(jq -r ".token" <<<"$json")
sessionid=$(jq -r ".sessionId" <<<"$json")
echo "Logged in session:$sessionid using token: $token"

curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X GET $BASEURL/v1/objects/sessions
curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X GET $BASEURL/v1/objects/storages/instance
# VSP5K only:
# curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X GET $BASEURL/v1/objects/storage-summaries/instance
curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X GET $BASEURL/v1/objects/mps
curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X GET $BASEURL/v1/objects/clprs
curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X GET $BASEURL//simple/v1/objects/qos-groups

echo "Logging out of session: $sessionid"
curl -k -H "Accept:application/json" -H "Content-Type:application/json" -H "Authorization:Session $token" -X DELETE $BASEURL/v1/objects/sessions/$sessionid
