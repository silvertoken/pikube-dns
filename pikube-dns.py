import kopf, logging, os, requests
import kubernetes.config as kconfig
import kubernetes.client as kclient

dns_crd = kclient.V1CustomResourceDefinition(
    api_version="apiextensions.k8s.io/v1",
    kind="CustomResourceDefinition",
    metadata=kclient.V1ObjectMeta(name="dns.operators.silvertoken.github.io"),
    spec=kclient.V1CustomResourceDefinitionSpec(
        group="operators.silvertoken.github.io",
        versions=[kclient.V1CustomResourceDefinitionVersion(
            name="v1",
            served=True,
            storage=True,
            schema=kclient.V1CustomResourceValidation(
                open_apiv3_schema=kclient.V1JSONSchemaProps(
                    type="object",
                    properties={
                        "spec": kclient.V1JSONSchemaProps(
                            type="object",
                            properties = {
                                "ip_address": kclient.V1JSONSchemaProps(type="string"),
                                "dns": kclient.V1JSONSchemaProps(type="string")
							}
                        ),
                        "status": kclient.V1JSONSchemaProps(
                            type="object",
                            x_kubernetes_preserve_unknown_fields=True
                        )
                    }
                )
            )
        )],
        scope="Namespaced",
        names=kclient.V1CustomResourceDefinitionNames(
            plural="dns",
            singular="dns",
            kind="DNS",
            short_names=["dns"]
        )
    )
)

try:
	kconfig.load_kube_config()
except kconfig.ConfigException:
	kconfig.load_incluster_config()

api = kclient.ApiextensionsV1Api()
try:
	api.create_custom_resource_definition(dns_crd)
except kclient.rest.ApiException as e:
	if e.status == 409:
		print("CRD already exists")
	else:
		raise e

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.peering.priority = 10
    
@kopf.on.create('operators.silvertoken.github.io', 'v1', 'dns')
def on_dns_create(namespace, spec, body, **kwargs):
	logging.debug(f"DNS create handler is called: {body}")

	app = kclient.AppsV1Api()
	core = kclient.CoreV1Api()
	ip_address = spec.get('ip_address')
	dns = spec.get('dns')
	router = os.getenv('ROUTER')
	user = os.getenv('USER')
	passwd = os.getenv('PASSWD')
	ca_verify = os.getenv('CA_VERIFY')

	if not ca_verify:
		ca_verify = True
	else:
		if ca_verify == 'False' or ca_verify == 'false':
			ca_verify = False
   
	if not router:
		logging.error("ROUTER environment variable is not set!")
		raise kopf.PermanentError("ROUTER environment variable is not set!")

	if not user or not passwd:
		logging.error("USER and PASSWD environment variables not set!")
		raise kopf.PermanentError("USER and PASSWD environment variables not set!")

	if not dns:
		logging.error("DNS name is required!")
		raise kopf.PermanentError("DNS name is required!")

	if not ip_address:
		'''TODO: Pick next available ip address'''
		logging.error("Next available IP address not implemented yet!")
		raise kopf.PermanentError("Next available IP address not implemented yet!")
	else:
		response = requests.get('https://' + router + '/rest/ip/dns/static', auth=(user, passwd), verify=ca_verify)
		logging.debug(f"GET current dns static list from '{router}'. status: {response.status_code}")
		if response.status_code == 200:
			address_list = response.json()
			for address in address_list:
				if address['name'] == dns:
					logging.error(f"DNS: '{dns}', already registered!")
					kopf.PermanentError(f"DNS: '{dns}', already registered!")

			logging.info(f"DNS: '{dns}' is available adding DNS record with IP: '{ip_address}'.")
			payload = {
				"address": ip_address,
				"name": dns
			}
   
			response = requests.put('https://' + router + '/rest/ip/dns/static',
                           auth=(user, passwd),
                           headers={"Content-Type": "application/json"},
                           json=payload,
                           verify=ca_verify)
			logging.debug(f"PUT dns '{dns}', with adddress '{address}'. status: {response.status_code}")
			if response.status_code == 201:
				logging.info(f"Successfully created DNS record '{dns}' with IP address '{address}'")
			else:
				logging.error(f"Failed to set DNS record '{dns}' with IP address '{address}'. status: '{response.status_code}' response: '{response.text}'")
				kopf.PermanentError(f"Failed to set DNS record '{dns}' with IP address '{address}'. status: '{response.status_code}' response: '{response.text}'")
		else:
			logging.error(f"Failed to get list of addresses. status: '{response.status_code}', response: '{response.text}'")
			kopf.TemporaryError(f"Failed to get list of addresses. status: '{response.status_code}', response: '{response.text}'", delay=30)
   
@kopf.on.delete('operators.silvertoken.github.io', 'v1', 'dns')
def on_dns_delete(namespace, spec, body, **kwargs):
	logging.debug(f"DNS delete handler is called: {body}")
	
	dns = spec.get('dns')
	router = os.getenv('ROUTER')
	user = os.getenv('USER')
	passwd = os.getenv('PASSWD')
	ca_verify = os.getenv('CA_VERIFY')

	if not ca_verify:
		ca_verify = True
	else:
		if ca_verify == 'False' or ca_verify == 'false':
			ca_verify = False
   
	if not router:
		logging.error("ROUTER environment variable is not set!")
		raise kopf.PermanentError("ROUTER environment variable is not set!")

	if not user or not passwd:
		logging.error("USER and PASSWD environment variables not set!")
		raise kopf.PermanentError("USER and PASSWD environment variables not set!")

	if not dns:
		logging.error("DNS name is required!")
		raise kopf.PermanentError("DNS name is required!")
	
	response = requests.get('https://' + router + '/rest/ip/dns/static', auth=(user, passwd), verify=ca_verify)
	logging.debug(f"GET current dns static list from '{router}'. status: {response.status_code}")
	if response.status_code == 200:
		address_list = response.json()
		for address in address_list:
			if address['name'] == dns:
				response = requests.delete('https://' + router + '/rest/ip/dns/static/' + address['.id'], auth=(user, passwd), verify=ca_verify)
				logging.debug(f"DELETE dns address with .id {address['.id']}. status: {response.status_code}")
				if response.status_code == 204:
					logging.info(f"Successfully removed DNS record '{dns}'")
				else:
					logging.error(f"Failed to remove DNS record '{dns}', status: '{response.status_code}, response: '{response.text}'")
					kopf.PermanentError(f"Failed to remove DNS record '{dns}', status: '{response.status_code}, response: '{response.text}'")
	else:
		logging.error(f"Failed to get list of addresses. status: '{response.status_code}', response: '{response.text}'")
		kopf.TemporaryError(f"Failed to get list of addresses. status: '{response.status_code}', response: '{response.text}'", delay=30)
