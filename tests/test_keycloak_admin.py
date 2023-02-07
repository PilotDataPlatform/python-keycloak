"""Test the keycloak admin object."""

import copy
from typing import Tuple

import pytest

import keycloak
from keycloak import KeycloakAdmin, KeycloakOpenID
from keycloak.connection import ConnectionManager
from keycloak.exceptions import (
    KeycloakAuthenticationError,
    KeycloakDeleteError,
    KeycloakGetError,
    KeycloakPostError,
    KeycloakPutError,
)


def test_keycloak_version():
    """Test version."""
    assert keycloak.__version__, keycloak.__version__


def test_keycloak_admin_bad_init(env):
    """Test keycloak admin bad init.

    :param env: Environment fixture
    :type env: KeycloakTestEnv
    """
    with pytest.raises(TypeError) as err:
        KeycloakAdmin(
            server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
            username=env.KEYCLOAK_ADMIN,
            password=env.KEYCLOAK_ADMIN_PASSWORD,
            auto_refresh_token=1,
        )
    assert err.match("Expected a list of strings")

    with pytest.raises(TypeError) as err:
        KeycloakAdmin(
            server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
            username=env.KEYCLOAK_ADMIN,
            password=env.KEYCLOAK_ADMIN_PASSWORD,
            auto_refresh_token=["patch"],
        )
    assert err.match("Unexpected method in auto_refresh_token")


@pytest.mark.asyncio
async def test_keycloak_admin_init(env):
    """Test keycloak admin init.

    :param env: Environment fixture
    :type env: KeycloakTestEnv
    """
    admin = KeycloakAdmin(
        server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
        username=env.KEYCLOAK_ADMIN,
        password=env.KEYCLOAK_ADMIN_PASSWORD,
    )
    await admin.connect()
    assert admin.server_url == f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}", admin.server_url
    assert admin.realm_name == "master", admin.realm_name
    assert isinstance(admin.connection, ConnectionManager), type(admin.connection)
    assert admin.client_id == "admin-cli", admin.client_id
    assert admin.client_secret_key is None, admin.client_secret_key
    assert admin.verify, admin.verify
    assert admin.username == env.KEYCLOAK_ADMIN, admin.username
    assert admin.password == env.KEYCLOAK_ADMIN_PASSWORD, admin.password
    assert admin.totp is None, admin.totp
    assert admin.token is not None, admin.token
    assert admin.auto_refresh_token == list(), admin.auto_refresh_token
    assert admin.user_realm_name is None, admin.user_realm_name
    assert admin.custom_headers is None, admin.custom_headers
    assert admin.token

    admin = KeycloakAdmin(
        server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
        username=env.KEYCLOAK_ADMIN,
        password=env.KEYCLOAK_ADMIN_PASSWORD,
        realm_name=None,
        user_realm_name="master",
    )
    await admin.connect()
    assert admin.token
    admin = KeycloakAdmin(
        server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
        username=env.KEYCLOAK_ADMIN,
        password=env.KEYCLOAK_ADMIN_PASSWORD,
        realm_name=None,
        user_realm_name=None,
    )
    await admin.connect()
    assert admin.token

    await admin.create_realm(payload={"realm": "authz", "enabled": True})
    admin.realm_name = "authz"
    await admin.create_client(
        payload={
            "name": "authz-client",
            "clientId": "authz-client",
            "authorizationServicesEnabled": True,
            "serviceAccountsEnabled": True,
            "clientAuthenticatorType": "client-secret",
            "directAccessGrantsEnabled": False,
            "enabled": True,
            "implicitFlowEnabled": False,
            "publicClient": False,
        }
    )
    client_id = await admin.get_client_id("authz-client")
    secret = await admin.generate_client_secrets(client_id=client_id)
    admin2 = KeycloakAdmin(
        server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
        user_realm_name="authz",
        client_id="authz-client",
        client_secret_key=secret["value"],
    )
    await admin2.connect()
    assert admin2.token

    await admin.delete_realm(realm_name="authz")

    assert (
        KeycloakAdmin(
            server_url=f"http://{env.KEYCLOAK_HOST}:{env.KEYCLOAK_PORT}",
            username=None,
            password=None,
            client_secret_key=None,
            custom_headers={"custom": "header"},
        ).token
        is None
    )


@pytest.mark.asyncio
async def test_realms(admin: KeycloakAdmin):
    """Test realms.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    """
    # Get realms
    realms = await admin.get_realms()
    assert len(realms) == 1, realms
    assert "master" == realms[0]["realm"]

    # Create a test realm
    res = await admin.create_realm(payload={"realm": "test"})
    assert res == b"", res

    # Create the same realm, should fail
    with pytest.raises(KeycloakPostError) as err:
        res = await admin.create_realm(payload={"realm": "test"})
    assert err.match('409: b\'{"errorMessage":"Conflict detected. See logs for details"}\'')

    # Create the same realm, skip_exists true
    res = await admin.create_realm(payload={"realm": "test"}, skip_exists=True)
    assert res == {"msg": "Already exists"}, res

    # Get a single realm
    res = await admin.get_realm(realm_name="test")
    assert res["realm"] == "test"

    # Get non-existing realm
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_realm(realm_name="non-existent")
    assert err.match('404: b\'{"error":"Realm not found."}\'')

    # Update realm
    res = await admin.update_realm(realm_name="test", payload={"accountTheme": "test"})
    assert res == dict(), res

    # Check that the update worked
    res = await admin.get_realm(realm_name="test")
    assert res["realm"] == "test"
    assert res["accountTheme"] == "test"

    # Update wrong payload
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_realm(realm_name="test", payload={"wrong": "payload"})
    assert err.match('400: b\'{"error":"Unrecognized field')

    # Check that get realms returns both realms
    realms = await admin.get_realms()
    realm_names = [x["realm"] for x in realms]
    assert len(realms) == 2, realms
    assert "master" in realm_names, realm_names
    assert "test" in realm_names, realm_names

    # Delete the realm
    res = await admin.delete_realm(realm_name="test")
    assert res == dict(), res

    # Check that the realm does not exist anymore
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_realm(realm_name="test")
    assert err.match('404: b\'{"error":"Realm not found."}\'')

    # Delete non-existing realm
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_realm(realm_name="non-existent")
    assert err.match('404: b\'{"error":"Realm not found."}\'')


@pytest.mark.asyncio
async def test_import_export_realms(admin: KeycloakAdmin, realm: str):
    """Test import and export of realms.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    realm_export = await admin.export_realm(export_clients=True, export_groups_and_role=True)
    assert realm_export != dict(), realm_export

    await admin.delete_realm(realm_name=realm)
    admin.realm_name = "master"
    res = await admin.import_realm(payload=realm_export)
    assert res == b"", res

    # Test bad import
    with pytest.raises(KeycloakPostError) as err:
        await admin.import_realm(payload=dict())
    assert err.match('500: b\'{"error":"unknown_error"}\'')


@pytest.mark.asyncio
async def test_users(admin: KeycloakAdmin, realm: str):
    """Test users.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Check no users present
    users = await admin.get_users()
    assert users == list(), users

    # Test create user
    user_id = await admin.create_user(payload={"username": "test", "email": "test@test.test"})
    assert user_id is not None, user_id

    # Test create the same user
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_user(payload={"username": "test", "email": "test@test.test"})
    assert err.match('409: b\'{"errorMessage":"User exists with same username"}\'')

    # Test create the same user, exists_ok true
    user_id_2 = await admin.create_user(
        payload={"username": "test", "email": "test@test.test"}, exist_ok=True
    )
    assert user_id == user_id_2

    # Test get user
    user = await admin.get_user(user_id=user_id)
    assert user["username"] == "test", user["username"]
    assert user["email"] == "test@test.test", user["email"]

    # Test update user
    res = await admin.update_user(user_id=user_id, payload={"firstName": "Test"})
    assert res == dict(), res
    user = await admin.get_user(user_id=user_id)
    assert user["firstName"] == "Test"

    # Test update user fail
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_user(user_id=user_id, payload={"wrong": "payload"})
    assert err.match('400: b\'{"error":"Unrecognized field')

    # Test get users again
    users = await admin.get_users()
    usernames = [x["username"] for x in users]
    assert "test" in usernames

    # Test users counts
    count = await admin.users_count()
    assert count == 1, count

    # Test users count with query
    count = await admin.users_count(query={"username": "notpresent"})
    assert count == 0

    # Test user groups
    groups = await admin.get_user_groups(user_id=user["id"])
    assert len(groups) == 0

    # Test user groups bad id
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_user_groups(user_id="does-not-exist")
    assert err.match('404: b\'{"error":"User not found"}\'')

    # Test logout
    res = await admin.user_logout(user_id=user["id"])
    assert res == dict(), res

    # Test logout fail
    with pytest.raises(KeycloakPostError) as err:
        await admin.user_logout(user_id="non-existent-id")
    assert err.match('404: b\'{"error":"User not found"}\'')

    # Test consents
    res = await admin.user_consents(user_id=user["id"])
    assert len(res) == 0, res

    # Test consents fail
    with pytest.raises(KeycloakGetError) as err:
        await admin.user_consents(user_id="non-existent-id")
    assert err.match('404: b\'{"error":"User not found"}\'')

    # Test delete user
    res = await admin.delete_user(user_id=user_id)
    assert res == dict(), res
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_user(user_id=user_id)
    err.match('404: b\'{"error":"User not found"}\'')

    # Test delete fail
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_user(user_id="non-existent-id")
    assert err.match('404: b\'{"error":"User not found"}\'')


@pytest.mark.asyncio
async def test_users_pagination(admin: KeycloakAdmin, realm: str):
    """Test user pagination.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    for ind in range(admin.PAGE_SIZE + 50):
        username = f"user_{ind}"
        await admin.create_user(payload={"username": username, "email": f"{username}@test.test"})

    users = await admin.get_users()
    assert len(users) == admin.PAGE_SIZE + 50, len(users)

    users = await admin.get_users(query={"first": 100})
    assert len(users) == 50, len(users)

    users = await admin.get_users(query={"max": 20})
    assert len(users) == 20, len(users)


@pytest.mark.asyncio
async def test_idps(admin: KeycloakAdmin, realm: str):
    """Test IDPs.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Create IDP
    res = await admin.create_idp(
        payload=dict(
            providerId="github", alias="github", config=dict(clientId="test", clientSecret="test")
        )
    )
    assert res == b"", res

    # Test create idp fail
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_idp(payload={"providerId": "does-not-exist", "alias": "something"})
    assert err.match("Invalid identity provider id"), err

    # Test listing
    idps = await admin.get_idps()
    assert len(idps) == 1
    assert "github" == idps[0]["alias"]

    # Test IdP update
    res = await admin.update_idp(idp_alias="github", payload=idps[0])

    assert res == {}, res

    # Test adding a mapper
    res = await admin.add_mapper_to_idp(
        idp_alias="github",
        payload={
            "identityProviderAlias": "github",
            "identityProviderMapper": "github-user-attribute-mapper",
            "name": "test",
        },
    )
    assert res == b"", res

    # Test mapper fail
    with pytest.raises(KeycloakPostError) as err:
        await admin.add_mapper_to_idp(idp_alias="does-no-texist", payload=dict())
    assert err.match('404: b\'{"error":"HTTP 404 Not Found"}\'')

    # Test IdP mappers listing
    idp_mappers = await admin.get_idp_mappers(idp_alias="github")
    assert len(idp_mappers) == 1

    # Test IdP mapper update
    res = await admin.update_mapper_in_idp(
        idp_alias="github",
        mapper_id=idp_mappers[0]["id"],
        # For an obscure reason, keycloak expect all fields
        payload={
            "id": idp_mappers[0]["id"],
            "identityProviderAlias": "github-alias",
            "identityProviderMapper": "github-user-attribute-mapper",
            "name": "test",
            "config": idp_mappers[0]["config"],
        },
    )
    assert res == dict(), res

    # Test delete
    res = await admin.delete_idp(idp_alias="github")
    assert res == dict(), res

    # Test delete fail
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_idp(idp_alias="does-not-exist")
    assert err.match('404: b\'{"error":"HTTP 404 Not Found"}\'')


@pytest.mark.asyncio
async def test_user_credentials(admin: KeycloakAdmin, user: str):
    """Test user credentials.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param user: Keycloak user
    :type user: str
    """
    res = await admin.set_user_password(user_id=user, password="booya", temporary=True)
    assert res == dict(), res

    # Test user password set fail
    with pytest.raises(KeycloakPutError) as err:
        await admin.set_user_password(user_id="does-not-exist", password="")
    assert err.match('404: b\'{"error":"User not found"}\'')

    credentials = await admin.get_credentials(user_id=user)
    assert len(credentials) == 1
    assert credentials[0]["type"] == "password", credentials

    # Test get credentials fail
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_credentials(user_id="does-not-exist")
    assert err.match('404: b\'{"error":"User not found"}\'')

    res = await admin.delete_credential(user_id=user, credential_id=credentials[0]["id"])
    assert res == dict(), res

    # Test delete fail
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_credential(user_id=user, credential_id="does-not-exist")
    assert err.match('404: b\'{"error":"Credential not found"}\'')


@pytest.mark.asyncio
async def test_social_logins(admin: KeycloakAdmin, user: str):
    """Test social logins.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param user: Keycloak user
    :type user: str
    """
    res = await admin.add_user_social_login(
        user_id=user, provider_id="gitlab", provider_userid="test", provider_username="test"
    )
    assert res == dict(), res
    await admin.add_user_social_login(
        user_id=user, provider_id="github", provider_userid="test", provider_username="test"
    )
    assert res == dict(), res

    # Test add social login fail
    with pytest.raises(KeycloakPostError) as err:
        await admin.add_user_social_login(
            user_id="does-not-exist",
            provider_id="does-not-exist",
            provider_userid="test",
            provider_username="test",
        )
    assert err.match('404: b\'{"error":"User not found"}\'')

    res = await admin.get_user_social_logins(user_id=user)
    assert res == list(), res

    # Test get social logins fail
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_user_social_logins(user_id="does-not-exist")
    assert err.match('404: b\'{"error":"User not found"}\'')

    res = await admin.delete_user_social_login(user_id=user, provider_id="gitlab")
    assert res == {}, res

    res = await admin.delete_user_social_login(user_id=user, provider_id="github")
    assert res == {}, res

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_user_social_login(user_id=user, provider_id="instagram")
    assert err.match('404: b\'{"error":"Link not found"}\''), err


@pytest.mark.asyncio
async def test_server_info(admin: KeycloakAdmin):
    """Test server info.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    """
    info = await admin.get_server_info()
    assert set(info.keys()).issubset(
        {
            "systemInfo",
            "memoryInfo",
            "profileInfo",
            "themes",
            "socialProviders",
            "identityProviders",
            "providers",
            "protocolMapperTypes",
            "builtinProtocolMappers",
            "clientInstallations",
            "componentTypes",
            "passwordPolicies",
            "enums",
            "cryptoInfo",
        }
    ), info.keys()


@pytest.mark.asyncio
async def test_groups(admin: KeycloakAdmin, user: str):
    """Test groups.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param user: Keycloak user
    :type user: str
    """
    # Test get groups
    groups = await admin.get_groups()
    assert len(groups) == 0

    # Test create group
    group_id = await admin.create_group(payload={"name": "main-group"})
    assert group_id is not None, group_id

    # Test create subgroups
    subgroup_id_1 = await admin.create_group(payload={"name": "subgroup-1"}, parent=group_id)
    subgroup_id_2 = await admin.create_group(payload={"name": "subgroup-2"}, parent=group_id)

    # Test create group fail
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_group(payload={"name": "subgroup-1"}, parent=group_id)
    assert err.match('409: b\'{"error":"unknown_error"}\''), err

    # Test skip exists OK
    subgroup_id_1_eq = await admin.create_group(
        payload={"name": "subgroup-1"}, parent=group_id, skip_exists=True
    )
    assert subgroup_id_1_eq is None

    # Test get groups again
    groups = await admin.get_groups()
    assert len(groups) == 1, groups
    assert len(groups[0]["subGroups"]) == 2, groups["subGroups"]
    assert groups[0]["id"] == group_id
    assert {x["id"] for x in groups[0]["subGroups"]} == {subgroup_id_1, subgroup_id_2}

    # Test get groups query
    groups = await admin.get_groups(query={"max": 10})
    assert len(groups) == 1, groups
    assert len(groups[0]["subGroups"]) == 2, groups["subGroups"]
    assert groups[0]["id"] == group_id
    assert {x["id"] for x in groups[0]["subGroups"]} == {subgroup_id_1, subgroup_id_2}

    # Test get group
    res = await admin.get_group(group_id=subgroup_id_1)
    assert res["id"] == subgroup_id_1, res
    assert res["name"] == "subgroup-1"
    assert res["path"] == "/main-group/subgroup-1"

    # Test get group fail
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_group(group_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find group by id"}\''), err

    # Create 1 more subgroup
    subsubgroup_id_1 = await admin.create_group(payload={"name": "subsubgroup-1"}, parent=subgroup_id_2)
    main_group = await admin.get_group(group_id=group_id)

    # Test nested searches
    res = await admin.get_subgroups(group=main_group, path="/main-group/subgroup-2/subsubgroup-1")
    assert res is not None, res
    assert res["id"] == subsubgroup_id_1

    # Test empty search
    res = await admin.get_subgroups(group=main_group, path="/none")
    assert res is None, res

    # Test get group by path
    res = await admin.get_group_by_path(path="/main-group/subgroup-1")
    assert res is None, res

    res = await admin.get_group_by_path(path="/main-group/subgroup-1", search_in_subgroups=True)
    assert res is not None, res
    assert res["id"] == subgroup_id_1, res

    res = await admin.get_group_by_path(
        path="/main-group/subgroup-2/subsubgroup-1/test", search_in_subgroups=True
    )
    assert res is None, res

    res = await admin.get_group_by_path(
        path="/main-group/subgroup-2/subsubgroup-1", search_in_subgroups=True
    )
    assert res is not None, res
    assert res["id"] == subsubgroup_id_1

    res = await admin.get_group_by_path(path="/main-group")
    assert res is not None, res
    assert res["id"] == group_id, res

    # Test group members
    res = await admin.get_group_members(group_id=subgroup_id_2)
    assert len(res) == 0, res

    # Test fail group members
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_group_members(group_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find group by id"}\'')

    res = await admin.group_user_add(user_id=user, group_id=subgroup_id_2)
    assert res == dict(), res

    res = await admin.get_group_members(group_id=subgroup_id_2)
    assert len(res) == 1, res
    assert res[0]["id"] == user

    # Test get group members query
    res = await admin.get_group_members(group_id=subgroup_id_2, query={"max": 10})
    assert len(res) == 1, res
    assert res[0]["id"] == user

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.group_user_remove(user_id="does-not-exist", group_id=subgroup_id_2)
    assert err.match('404: b\'{"error":"User not found"}\''), err

    res = await admin.group_user_remove(user_id=user, group_id=subgroup_id_2)
    assert res == dict(), res

    # Test set permissions
    res = await admin.group_set_permissions(group_id=subgroup_id_2, enabled=True)
    assert res["enabled"], res
    res = await admin.group_set_permissions(group_id=subgroup_id_2, enabled=False)
    assert not res["enabled"], res
    with pytest.raises(KeycloakPutError) as err:
        await admin.group_set_permissions(group_id=subgroup_id_2, enabled="blah")
    assert err.match('500: b\'{"error":"unknown_error"}\''), err

    # Test update group
    res = await admin.update_group(group_id=subgroup_id_2, payload={"name": "new-subgroup-2"})
    assert res == dict(), res
    group = await admin.get_group(group_id=subgroup_id_2)
    assert group["name"] == "new-subgroup-2"

    # test update fail
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_group(group_id="does-not-exist", payload=dict())
    assert err.match('404: b\'{"error":"Could not find group by id"}\''), err

    # Test delete
    res = await admin.delete_group(group_id=group_id)
    assert res == dict(), res
    groups = await admin.get_groups()
    assert len(groups) == 0

    # Test delete fail
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_group(group_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find group by id"}\''), err


@pytest.mark.asyncio
async def test_clients(admin: KeycloakAdmin, realm: str):
    """Test clients.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Test get clients
    clients = await admin.get_clients()
    assert len(clients) == 6, clients
    assert {x["name"] for x in clients} == set(
        [
            "${client_admin-cli}",
            "${client_security-admin-console}",
            "${client_account-console}",
            "${client_broker}",
            "${client_account}",
            "${client_realm-management}",
        ]
    ), clients

    # Test create client
    client_id = await admin.create_client(payload={"name": "test-client", "clientId": "test-client"})
    assert client_id, client_id

    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client(payload={"name": "test-client", "clientId": "test-client"})
    assert err.match('409: b\'{"errorMessage":"Client test-client already exists"}\''), err

    client_id_2 = await admin.create_client(
        payload={"name": "test-client", "clientId": "test-client"}, skip_exists=True
    )
    assert client_id == client_id_2, client_id_2

    # Test get client
    res = await admin.get_client(client_id=client_id)
    assert res["clientId"] == "test-client", res
    assert res["name"] == "test-client", res
    assert res["id"] == client_id, res

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client(client_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client"}\'')
    assert len(await admin.get_clients()) == 7

    # Test get client id
    assert await admin.get_client_id(client_id="test-client") == client_id
    assert await admin.get_client_id(client_id="does-not-exist") is None

    # Test update client
    res = await admin.update_client(client_id=client_id, payload={"name": "test-client-change"})
    assert res == dict(), res

    with pytest.raises(KeycloakPutError) as err:
        await admin.update_client(client_id="does-not-exist", payload={"name": "test-client-change"})
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    # Test client mappers
    res = await admin.get_mappers_from_client(client_id=client_id)
    assert len(res) == 0

    with pytest.raises(KeycloakPostError) as err:
        await admin.add_mapper_to_client(client_id="does-not-exist", payload=dict())
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    res = await admin.add_mapper_to_client(
        client_id=client_id,
        payload={
            "name": "test-mapper",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
        },
    )
    assert res == b""
    assert len(await admin.get_mappers_from_client(client_id=client_id)) == 1

    mappers = await admin.get_mappers_from_client(client_id=client_id)
    mapper = mappers[0]
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_client_mapper(client_id=client_id, mapper_id="does-not-exist", payload=dict())
    assert err.match('404: b\'{"error":"Model not found"}\'')
    mapper["config"]["user.attribute"] = "test"
    res = await admin.update_client_mapper(client_id=client_id, mapper_id=mapper["id"], payload=mapper)
    assert res == dict()

    res = await admin.remove_client_mapper(client_id=client_id, client_mapper_id=mapper["id"])
    assert res == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.remove_client_mapper(client_id=client_id, client_mapper_id=mapper["id"])
    assert err.match('404: b\'{"error":"Model not found"}\'')

    # Test client sessions
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_all_sessions(client_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    assert await admin.get_client_all_sessions(client_id=client_id) == list()
    assert await admin.get_client_sessions_stats() == list()

    # Test authz
    auth_client_id = await admin.create_client(
        payload={
            "name": "authz-client",
            "clientId": "authz-client",
            "authorizationServicesEnabled": True,
            "serviceAccountsEnabled": True,
        }
    )
    res = await admin.get_client_authz_settings(client_id=auth_client_id)
    assert res["allowRemoteResourceManagement"]
    assert res["decisionStrategy"] == "UNANIMOUS"
    assert len(res["policies"]) >= 0

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_authz_settings(client_id=client_id)
    assert err.match('404: b\'{"error":"HTTP 404 Not Found"}\'')

    # Authz resources
    res = await admin.get_client_authz_resources(client_id=auth_client_id)
    assert len(res) == 1
    assert res[0]["name"] == "Default Resource"

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_authz_resources(client_id=client_id)
    assert err.match('404: b\'{"error":"HTTP 404 Not Found"}\'')

    res = await admin.create_client_authz_resource(
        client_id=auth_client_id, payload={"name": "test-resource"}
    )
    assert res["name"] == "test-resource", res
    test_resource_id = res["_id"]

    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client_authz_resource(
            client_id=auth_client_id, payload={"name": "test-resource"}
        )
    assert err.match('409: b\'{"error":"invalid_request"')
    assert await admin.create_client_authz_resource(
        client_id=auth_client_id, payload={"name": "test-resource"}, skip_exists=True
    ) == {"msg": "Already exists"}

    res = await admin.get_client_authz_resources(client_id=auth_client_id)
    assert len(res) == 2
    assert {x["name"] for x in res} == {"Default Resource", "test-resource"}

    # Authz policies
    res = await admin.get_client_authz_policies(client_id=auth_client_id)
    assert len(res) == 1, res
    assert res[0]["name"] == "Default Policy"

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_authz_policies(client_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    role = await admin.get_realm_role(role_name="offline_access")
    role_id = role["id"]
    res = await admin.create_client_authz_role_based_policy(
        client_id=auth_client_id,
        payload={"name": "test-authz-rb-policy", "roles": [{"id": role_id}]},
    )
    assert res["name"] == "test-authz-rb-policy", res

    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client_authz_role_based_policy(
            client_id=auth_client_id,
            payload={"name": "test-authz-rb-policy", "roles": [{"id": role_id}]},
        )
    assert err.match('409: b\'{"error":"Policy with name')
    assert await admin.create_client_authz_role_based_policy(
        client_id=auth_client_id,
        payload={"name": "test-authz-rb-policy", "roles": [{"id": role_id}]},
        skip_exists=True,
    ) == {"msg": "Already exists"}
    assert len(await admin.get_client_authz_policies(client_id=auth_client_id)) == 2

    # Test authz permissions
    res = await admin.get_client_authz_permissions(client_id=auth_client_id)
    assert len(res) == 1, res
    assert res[0]["name"] == "Default Permission"

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_authz_permissions(client_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    res = await admin.create_client_authz_resource_based_permission(
        client_id=auth_client_id,
        payload={"name": "test-permission-rb", "resources": [test_resource_id]},
    )
    assert res, res
    assert res["name"] == "test-permission-rb"
    assert res["resources"] == [test_resource_id]

    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client_authz_resource_based_permission(
            client_id=auth_client_id,
            payload={"name": "test-permission-rb", "resources": [test_resource_id]},
        )
    assert err.match('409: b\'{"error":"Policy with name')
    assert await admin.create_client_authz_resource_based_permission(
        client_id=auth_client_id,
        payload={"name": "test-permission-rb", "resources": [test_resource_id]},
        skip_exists=True,
    ) == {"msg": "Already exists"}
    assert len(await admin.get_client_authz_permissions(client_id=auth_client_id)) == 2

    # Test authz scopes
    res = await admin.get_client_authz_scopes(client_id=auth_client_id)
    assert len(res) == 0, res

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_authz_scopes(client_id=client_id)
    assert err.match('404: b\'{"error":"HTTP 404 Not Found"}\'')

    res = await admin.create_client_authz_scopes(
        client_id=auth_client_id, payload={"name": "test-authz-scope"}
    )
    assert res["name"] == "test-authz-scope", res

    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client_authz_scopes(
            client_id="invalid_client_id", payload={"name": "test-authz-scope"}
        )
    assert err.match('404: b\'{"error":"Could not find client"')
    assert await admin.create_client_authz_scopes(
        client_id=auth_client_id, payload={"name": "test-authz-scope"}
    )

    res = await admin.get_client_authz_scopes(client_id=auth_client_id)
    assert len(res) == 1
    assert {x["name"] for x in res} == {"test-authz-scope"}

    # Test service account user
    res = await admin.get_client_service_account_user(client_id=auth_client_id)
    assert res["username"] == "service-account-authz-client", res

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_service_account_user(client_id=client_id)
    assert err.match('400: b\'{"error":"unknown_error"}\'')

    # Test delete client
    res = await admin.delete_client(client_id=auth_client_id)
    assert res == dict(), res
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_client(client_id=auth_client_id)
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    # Test client credentials
    await admin.create_client(
        payload={
            "name": "test-confidential",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "redirectUris": ["http://localhost/*"],
            "webOrigins": ["+"],
            "clientId": "test-confidential",
            "secret": "test-secret",
            "clientAuthenticatorType": "client-secret",
        }
    )
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_secrets(client_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    secrets = await admin.get_client_secrets(
        client_id=await admin.get_client_id(client_id="test-confidential")
    )
    assert secrets == {"type": "secret", "value": "test-secret"}

    with pytest.raises(KeycloakPostError) as err:
        await admin.generate_client_secrets(client_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    res = await admin.generate_client_secrets(
        client_id=await admin.get_client_id(client_id="test-confidential")
    )
    assert res
    assert (
        await admin.get_client_secrets(client_id=await admin.get_client_id(client_id="test-confidential"))
        == res
    )


@pytest.mark.asyncio
async def test_realm_roles(admin: KeycloakAdmin, realm: str):
    """Test realm roles.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Test get realm roles
    roles = await admin.get_realm_roles()
    assert len(roles) == 3, roles
    role_names = [x["name"] for x in roles]
    assert "uma_authorization" in role_names, role_names
    assert "offline_access" in role_names, role_names

    # Test empty members
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_realm_role_members(role_name="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find role"}\'')
    members = await admin.get_realm_role_members(role_name="offline_access")
    assert members == list(), members

    # Test create realm role
    role_id = await admin.create_realm_role(payload={"name": "test-realm-role"}, skip_exists=True)
    assert role_id, role_id
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_realm_role(payload={"name": "test-realm-role"})
    assert err.match('409: b\'{"errorMessage":"Role with name test-realm-role already exists"}\'')
    role_id_2 = await admin.create_realm_role(payload={"name": "test-realm-role"}, skip_exists=True)
    assert role_id == role_id_2

    # Test update realm role
    res = await admin.update_realm_role(
        role_name="test-realm-role", payload={"name": "test-realm-role-update"}
    )
    assert res == dict(), res
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_realm_role(
            role_name="test-realm-role", payload={"name": "test-realm-role-update"}
        )
    assert err.match('404: b\'{"error":"Could not find role"}\''), err

    # Test realm role user assignment
    user_id = await admin.create_user(payload={"username": "role-testing", "email": "test@test.test"})
    with pytest.raises(KeycloakPostError) as err:
        await admin.assign_realm_roles(user_id=user_id, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.assign_realm_roles(
        user_id=user_id,
        roles=[
            await admin.get_realm_role(role_name="offline_access"),
            await admin.get_realm_role(role_name="test-realm-role-update"),
        ],
    )
    assert res == dict(), res
    user = await admin.get_user(user_id=user_id)
    assert user["username"] in [
        x["username"] for x in await admin.get_realm_role_members(role_name="offline_access")
    ]

    user = await admin.get_user(user_id=user_id)
    assert user["username"] in [
        x["username"]
        for x in await admin.get_realm_role_members(role_name="test-realm-role-update")
    ]

    roles = await admin.get_realm_roles_of_user(user_id=user_id)
    assert len(roles) == 3
    assert "offline_access" in [x["name"] for x in roles]
    assert "test-realm-role-update" in [x["name"] for x in roles]

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_realm_roles_of_user(user_id=user_id, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.delete_realm_roles_of_user(
        user_id=user_id, roles=[await admin.get_realm_role(role_name="offline_access")]
    )
    assert res == dict(), res
    assert await admin.get_realm_role_members(role_name="offline_access") == list()
    roles = await admin.get_realm_roles_of_user(user_id=user_id)
    assert len(roles) == 2
    assert "offline_access" not in [x["name"] for x in roles]
    assert "test-realm-role-update" in [x["name"] for x in roles]

    roles = await admin.get_available_realm_roles_of_user(user_id=user_id)
    assert len(roles) == 2
    assert "offline_access" in [x["name"] for x in roles]
    assert "uma_authorization" in [x["name"] for x in roles]

    # Test realm role group assignment
    group_id = await admin.create_group(payload={"name": "test-group"})
    with pytest.raises(KeycloakPostError) as err:
        await admin.assign_group_realm_roles(group_id=group_id, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')

    roles = [
        await admin.get_realm_role(role_name="offline_access"),
        await admin.get_realm_role(role_name="test-realm-role-update"),
    ]
    res = await admin.assign_group_realm_roles(
        group_id=group_id,
        roles=roles
    )
    assert res == dict(), res

    roles = await admin.get_group_realm_roles(group_id=group_id)
    assert len(roles) == 2
    assert "offline_access" in [x["name"] for x in roles]
    assert "test-realm-role-update" in [x["name"] for x in roles]

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_group_realm_roles(group_id=group_id, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.delete_group_realm_roles(
        group_id=group_id, roles=[await admin.get_realm_role(role_name="offline_access")]
    )
    assert res == dict(), res
    roles = await admin.get_group_realm_roles(group_id=group_id)
    assert len(roles) == 1
    assert "test-realm-role-update" in [x["name"] for x in roles]

    # Test composite realm roles
    composite_role = await admin.create_realm_role(payload={"name": "test-composite-role"})
    with pytest.raises(KeycloakPostError) as err:
        await admin.add_composite_realm_roles_to_role(role_name=composite_role, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.add_composite_realm_roles_to_role(
        role_name=composite_role, roles=[await admin.get_realm_role(role_name="test-realm-role-update")]
    )
    assert res == dict(), res

    res = await admin.get_composite_realm_roles_of_role(role_name=composite_role)
    assert len(res) == 1
    assert "test-realm-role-update" in res[0]["name"]
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_composite_realm_roles_of_role(role_name="bad")
    assert err.match('404: b\'{"error":"Could not find role"}\'')

    res = await admin.get_composite_realm_roles_of_user(user_id=user_id)
    assert len(res) == 4
    assert "offline_access" in {x["name"] for x in res}
    assert "test-realm-role-update" in {x["name"] for x in res}
    assert "uma_authorization" in {x["name"] for x in res}
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_composite_realm_roles_of_user(user_id="bad")
    assert err.match('404: b\'{"error":"User not found"}\'')

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.remove_composite_realm_roles_to_role(role_name=composite_role, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.remove_composite_realm_roles_to_role(
        role_name=composite_role, roles=[await admin.get_realm_role(role_name="test-realm-role-update")]
    )
    assert res == dict(), res

    res = await admin.get_composite_realm_roles_of_role(role_name=composite_role)
    assert len(res) == 0

    # Test delete realm role
    res = await admin.delete_realm_role(role_name=composite_role)
    assert res == dict(), res
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_realm_role(role_name=composite_role)
    assert err.match('404: b\'{"error":"Could not find role"}\'')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "testcase, arg_brief_repr, includes_attributes",
    [
        ("brief True", {"brief_representation": True}, False),
        ("brief False", {"brief_representation": False}, True),
        ("default", {}, False),
    ],
)
async def test_role_attributes(
    admin: KeycloakAdmin,
    realm: str,
    client: str,
    arg_brief_repr: dict,
    includes_attributes: bool,
    testcase: str,
):
    """Test getting role attributes for bulk calls.

    :param admin: Keycloak admin
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    :param client: Keycloak client
    :type client: str
    :param arg_brief_repr: Brief representation
    :type arg_brief_repr: dict
    :param includes_attributes: Indicator whether to include attributes
    :type includes_attributes: bool
    :param testcase: Test case
    :type testcase: str
    """
    # setup
    attribute_role = "test-realm-role-w-attr"
    test_attrs = {"attr1": ["val1"], "attr2": ["val2-1", "val2-2"]}
    role_id = await admin.create_realm_role(
        payload={"name": attribute_role, "attributes": test_attrs}, skip_exists=True
    )
    assert role_id, role_id

    cli_role_id = await admin.create_client_role(
        client, payload={"name": attribute_role, "attributes": test_attrs}, skip_exists=True
    )
    assert cli_role_id, cli_role_id

    if not includes_attributes:
        test_attrs = None

    # tests
    roles = await admin.get_realm_roles(**arg_brief_repr)
    roles_filtered = [role for role in roles if role["name"] == role_id]
    assert roles_filtered, roles_filtered
    role = roles_filtered[0]
    assert role.get("attributes") == test_attrs, testcase

    roles = await admin.get_client_roles(client, **arg_brief_repr)
    roles_filtered = [role for role in roles if role["name"] == cli_role_id]
    assert roles_filtered, roles_filtered
    role = roles_filtered[0]
    assert role.get("attributes") == test_attrs, testcase

    # cleanup
    res = await admin.delete_realm_role(role_name=attribute_role)
    assert res == dict(), res

    res = await admin.delete_client_role(client, role_name=attribute_role)
    assert res == dict(), res


@pytest.mark.asyncio
async def test_client_scope_realm_roles(admin: KeycloakAdmin, realm: str):
    """Test client realm roles.

    :param admin: Keycloak admin
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Test get realm roles
    roles = await admin.get_realm_roles()
    assert len(roles) == 3, roles
    role_names = [x["name"] for x in roles]
    assert "uma_authorization" in role_names, role_names
    assert "offline_access" in role_names, role_names

    # create realm role for test
    role_id = await admin.create_realm_role(payload={"name": "test-realm-role"}, skip_exists=True)
    assert role_id, role_id

    # Test realm role client assignment
    client_id = await admin.create_client(
        payload={"name": "role-testing-client", "clientId": "role-testing-client"}
    )
    with pytest.raises(KeycloakPostError) as err:
        await admin.assign_realm_roles_to_client_scope(client_id=client_id, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')

    roles = [
        await admin.get_realm_role(role_name="offline_access"),
        await admin.get_realm_role(role_name="test-realm-role"),
    ]
    res = await admin.assign_realm_roles_to_client_scope(
        client_id=client_id,
        roles=roles
    )
    assert res == dict(), res

    roles = await admin.get_realm_roles_of_client_scope(client_id=client_id)
    assert len(roles) == 2
    client_role_names = [x["name"] for x in roles]
    assert "offline_access" in client_role_names, client_role_names
    assert "test-realm-role" in client_role_names, client_role_names
    assert "uma_authorization" not in client_role_names, client_role_names

    # Test remove realm role of client
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_realm_roles_of_client_scope(client_id=client_id, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')

    roles = [await admin.get_realm_role(role_name="offline_access")]
    res = await admin.delete_realm_roles_of_client_scope(
        client_id=client_id, roles=roles
    )
    assert res == dict(), res
    roles = await admin.get_realm_roles_of_client_scope(client_id=client_id)
    assert len(roles) == 1
    assert "test-realm-role" in [x["name"] for x in roles]

    roles = [await admin.get_realm_role(role_name="test-realm-role")]
    res = await admin.delete_realm_roles_of_client_scope(
        client_id=client_id, roles=roles
    )
    assert res == dict(), res
    roles = await admin.get_realm_roles_of_client_scope(client_id=client_id)
    assert len(roles) == 0


@pytest.mark.asyncio
async def test_client_scope_client_roles(admin: KeycloakAdmin, realm: str, client: str):
    """Test client assignment of other client roles.

    :param admin: Keycloak admin
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    :param client: Keycloak client
    :type client: str
    """
    admin.realm_name = realm

    client_id = await admin.create_client(
        payload={"name": "role-testing-client", "clientId": "role-testing-client"}
    )

    # Test get client roles
    roles = await admin.get_client_roles_of_client_scope(client_id, client)
    assert len(roles) == 0, roles

    # create client role for test
    client_role_id = await admin.create_client_role(
        client_role_id=client, payload={"name": "client-role-test"}, skip_exists=True
    )
    assert client_role_id, client_role_id

    # Test client role assignment to other client
    with pytest.raises(KeycloakPostError) as err:
        await admin.assign_client_roles_to_client_scope(
            client_id=client_id, client_roles_owner_id=client, roles=["bad"]
        )
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.assign_client_roles_to_client_scope(
        client_id=client_id,
        client_roles_owner_id=client,
        roles=[await admin.get_client_role(client_id=client, role_name="client-role-test")],
    )
    assert res == dict(), res

    roles = await admin.get_client_roles_of_client_scope(
        client_id=client_id, client_roles_owner_id=client
    )
    assert len(roles) == 1
    client_role_names = [x["name"] for x in roles]
    assert "client-role-test" in client_role_names, client_role_names

    # Test remove realm role of client
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_client_roles_of_client_scope(
            client_id=client_id, client_roles_owner_id=client, roles=["bad"]
        )
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.delete_client_roles_of_client_scope(
        client_id=client_id,
        client_roles_owner_id=client,
        roles=[await admin.get_client_role(client_id=client, role_name="client-role-test")],
    )
    assert res == dict(), res
    roles = await admin.get_client_roles_of_client_scope(
        client_id=client_id, client_roles_owner_id=client
    )
    assert len(roles) == 0


@pytest.mark.asyncio
async def test_client_roles(admin: KeycloakAdmin, client: str):
    """Test client roles.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param client: Keycloak client
    :type client: str
    """
    # Test get client roles
    res = await admin.get_client_roles(client_id=client)
    assert len(res) == 0
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_roles(client_id="bad")
    assert err.match('404: b\'{"error":"Could not find client"}\'')

    # Test create client role
    client_role_id = await admin.create_client_role(
        client_role_id=client, payload={"name": "client-role-test"}, skip_exists=True
    )
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client_role(client_role_id=client, payload={"name": "client-role-test"})
    assert err.match('409: b\'{"errorMessage":"Role with name client-role-test already exists"}\'')
    client_role_id_2 = await admin.create_client_role(
        client_role_id=client, payload={"name": "client-role-test"}, skip_exists=True
    )
    assert client_role_id == client_role_id_2

    # Test get client role
    res = await admin.get_client_role(client_id=client, role_name="client-role-test")
    assert res["name"] == client_role_id
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_role(client_id=client, role_name="bad")
    assert err.match('404: b\'{"error":"Could not find role"}\'')

    res_ = await admin.get_client_role_id(client_id=client, role_name="client-role-test")
    assert res_ == res["id"]
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_role_id(client_id=client, role_name="bad")
    assert err.match('404: b\'{"error":"Could not find role"}\'')
    assert len(await admin.get_client_roles(client_id=client)) == 1

    # Test update client role
    res = await admin.update_client_role(
        client_role_id=client,
        role_name="client-role-test",
        payload={"name": "client-role-test-update"},
    )
    assert res == dict()
    with pytest.raises(KeycloakPutError) as err:
        res = await admin.update_client_role(
            client_role_id=client,
            role_name="client-role-test",
            payload={"name": "client-role-test-update"},
        )
    assert err.match('404: b\'{"error":"Could not find role"}\'')

    # Test user with client role
    res = await admin.get_client_role_members(client_id=client, role_name="client-role-test-update")
    assert len(res) == 0
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_role_members(client_id=client, role_name="bad")
    assert err.match('404: b\'{"error":"Could not find role"}\'')

    user_id = await admin.create_user(payload={"username": "test", "email": "test@test.test"})
    with pytest.raises(KeycloakPostError) as err:
        await admin.assign_client_role(user_id=user_id, client_id=client, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.assign_client_role(
        user_id=user_id,
        client_id=client,
        roles=[await admin.get_client_role(client_id=client, role_name="client-role-test-update")],
    )
    assert res == dict()
    assert (
        len(await admin.get_client_role_members(client_id=client, role_name="client-role-test-update"))
        == 1
    )

    roles = await admin.get_client_roles_of_user(user_id=user_id, client_id=client)
    assert len(roles) == 1, roles
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_roles_of_user(user_id=user_id, client_id="bad")
    assert err.match('404: b\'{"error":"Client not found"}\'')

    roles = await admin.get_composite_client_roles_of_user(user_id=user_id, client_id=client)
    assert len(roles) == 1, roles
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_composite_client_roles_of_user(user_id=user_id, client_id="bad")
    assert err.match('404: b\'{"error":"Client not found"}\'')

    roles = await admin.get_available_client_roles_of_user(user_id=user_id, client_id=client)
    assert len(roles) == 0, roles
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_composite_client_roles_of_user(user_id=user_id, client_id="bad")
    assert err.match('404: b\'{"error":"Client not found"}\'')

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_client_roles_of_user(user_id=user_id, client_id=client, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    await admin.delete_client_roles_of_user(
        user_id=user_id,
        client_id=client,
        roles=[await admin.get_client_role(client_id=client, role_name="client-role-test-update")],
    )
    assert len(await admin.get_client_roles_of_user(user_id=user_id, client_id=client)) == 0

    # Test groups and client roles
    res = await admin.get_client_role_groups(client_id=client, role_name="client-role-test-update")
    assert len(res) == 0
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_role_groups(client_id=client, role_name="bad")
    assert err.match('404: b\'{"error":"Could not find role"}\'')

    group_id = await admin.create_group(payload={"name": "test-group"})
    res = await admin.get_group_client_roles(group_id=group_id, client_id=client)
    assert len(res) == 0
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_group_client_roles(group_id=group_id, client_id="bad")
    assert err.match('404: b\'{"error":"Client not found"}\'')

    with pytest.raises(KeycloakPostError) as err:
        await admin.assign_group_client_roles(group_id=group_id, client_id=client, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.assign_group_client_roles(
        group_id=group_id,
        client_id=client,
        roles=[await admin.get_client_role(client_id=client, role_name="client-role-test-update")],
    )
    assert res == dict()
    assert (
        len(await admin.get_client_role_groups(client_id=client, role_name="client-role-test-update"))
        == 1
    )
    assert len(await admin.get_group_client_roles(group_id=group_id, client_id=client)) == 1

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_group_client_roles(group_id=group_id, client_id=client, roles=["bad"])
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.delete_group_client_roles(
        group_id=group_id,
        client_id=client,
        roles=[await admin.get_client_role(client_id=client, role_name="client-role-test-update")],
    )
    assert res == dict()

    # Test composite client roles
    with pytest.raises(KeycloakPostError) as err:
        await admin.add_composite_client_roles_to_role(
            client_role_id=client, role_name="client-role-test-update", roles=["bad"]
        )
    assert err.match('500: b\'{"error":"unknown_error"}\'')
    res = await admin.add_composite_client_roles_to_role(
        client_role_id=client,
        role_name="client-role-test-update",
        roles=[await admin.get_realm_role(role_name="offline_access")],
    )
    assert res == dict()
    role = await admin.get_client_role(client_id=client, role_name="client-role-test-update")
    assert role[
        "composite"
    ]

    # Test delete of client role
    res = await admin.delete_client_role(client_role_id=client, role_name="client-role-test-update")
    assert res == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_client_role(client_role_id=client, role_name="client-role-test-update")
    assert err.match('404: b\'{"error":"Could not find role"}\'')


@pytest.mark.asyncio
async def test_enable_token_exchange(admin: KeycloakAdmin, realm: str):
    """Test enable token exchange.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    :raises AssertionError: In case of bad configuration
    """
    # Test enabling token exchange between two confidential clients
    admin.realm_name = realm

    # Create test clients
    source_client_id = await admin.create_client(
        payload={"name": "Source Client", "clientId": "source-client"}
    )
    target_client_id = await admin.create_client(
        payload={"name": "Target Client", "clientId": "target-client"}
    )
    for c in await admin.get_clients():
        if c["clientId"] == "realm-management":
            realm_management_id = c["id"]
            break
    else:
        raise AssertionError("Missing realm management client")

    # Enable permissions on the Superset client
    await admin.update_client_management_permissions(
        payload={"enabled": True}, client_id=target_client_id
    )

    # Fetch various IDs and strings needed when creating the permission
    management_permissions = await admin.get_client_management_permissions(
        client_id=target_client_id
    )
    token_exchange_permission_id = management_permissions["scopePermissions"]["token-exchange"]
    scopes = await admin.get_client_authz_policy_scopes(
        client_id=realm_management_id, policy_id=token_exchange_permission_id
    )

    for s in scopes:
        if s["name"] == "token-exchange":
            token_exchange_scope_id = s["id"]
            break
    else:
        raise AssertionError("Missing token-exchange scope")

    resources = await admin.get_client_authz_policy_resources(
        client_id=realm_management_id, policy_id=token_exchange_permission_id
    )
    for r in resources:
        if r["name"] == f"client.resource.{target_client_id}":
            token_exchange_resource_id = r["_id"]
            break
    else:
        raise AssertionError("Missing client resource")

    # Create a client policy for source client
    policy_name = "Exchange source client token with target client token"
    client_policy = await admin.create_client_authz_client_policy(
        payload={
            "type": "client",
            "logic": "POSITIVE",
            "decisionStrategy": "UNANIMOUS",
            "name": policy_name,
            "clients": [source_client_id],
        },
        client_id=realm_management_id,
    )
    client_policy_id = client_policy["id"]
    policies = await admin.get_client_authz_client_policies(client_id=realm_management_id)
    for policy in policies:
        if policy["name"] == policy_name:
            assert policy["clients"] == [source_client_id]
            break
    else:
        raise AssertionError("Missing client policy")

    # Update permissions on the target client to reference this policy
    permission = await admin.get_client_authz_scope_permission(
        client_id=realm_management_id, scope_id=token_exchange_permission_id
    )
    permission_name = permission["name"]
    await admin.update_client_authz_scope_permission(
        payload={
            "id": token_exchange_permission_id,
            "name": permission_name,
            "type": "scope",
            "logic": "POSITIVE",
            "decisionStrategy": "UNANIMOUS",
            "resources": [token_exchange_resource_id],
            "scopes": [token_exchange_scope_id],
            "policies": [client_policy_id],
        },
        client_id=realm_management_id,
        scope_id=token_exchange_permission_id,
    )


@pytest.mark.asyncio
async def test_email(admin: KeycloakAdmin, user: str):
    """Test email.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param user: Keycloak user
    :type user: str
    """
    # Emails will fail as we don't have SMTP test setup
    with pytest.raises(KeycloakPutError) as err:
        await admin.send_update_account(user_id=user, payload=dict())
    #assert err.match('500: b\'{"error":"unknown_error"}\'')

    await admin.update_user(user_id=user, payload={"enabled": True})
    with pytest.raises(KeycloakPutError) as err:
        await admin.send_verify_email(user_id=user)
    #assert err.match('500: b\'{"errorMessage":"Failed to send execute actions email"}\'')


@pytest.mark.asyncio
async def test_get_sessions(admin: KeycloakAdmin):
    """Test get sessions.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    """
    sessions = await admin.get_sessions(user_id=await admin.get_user_id(username=admin.username))
    assert len(sessions) >= 1
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_sessions(user_id="bad")
    assert err.match('404: b\'{"error":"User not found"}\'')


@pytest.mark.asyncio
async def test_get_client_installation_provider(admin: KeycloakAdmin, client: str):
    """Test get client installation provider.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param client: Keycloak client
    :type client: str
    """
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_installation_provider(client_id=client, provider_id="bad")
    assert err.match('404: b\'{"error":"Unknown Provider"}\'')

    installation = await admin.get_client_installation_provider(
        client_id=client, provider_id="keycloak-oidc-keycloak-json"
    )
    assert set(installation.keys()) == {
        "auth-server-url",
        "confidential-port",
        "credentials",
        "realm",
        "resource",
        "ssl-required",
    }


@pytest.mark.asyncio
async def test_auth_flows(admin: KeycloakAdmin, realm: str):
    """Test auth flows.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    res = await admin.get_authentication_flows()
    assert len(res) == 8, res
    assert set(res[0].keys()) == {
        "alias",
        "authenticationExecutions",
        "builtIn",
        "description",
        "id",
        "providerId",
        "topLevel",
    }
    assert {x["alias"] for x in res} == {
        "reset credentials",
        "browser",
        "http challenge",
        "registration",
        "docker auth",
        "direct grant",
        "first broker login",
        "clients",
    }

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_authentication_flow_for_id(flow_id="bad")
    assert err.match('404: b\'{"error":"Could not find flow with id"}\'')
    browser_flow_id = [x for x in res if x["alias"] == "browser"][0]["id"]
    res = await admin.get_authentication_flow_for_id(flow_id=browser_flow_id)
    assert res["alias"] == "browser"

    # Test copying
    with pytest.raises(KeycloakPostError) as err:
        await admin.copy_authentication_flow(payload=dict(), flow_alias="bad")
    assert err.match("404: b''")

    res = await admin.copy_authentication_flow(payload={"newName": "test-browser"}, flow_alias="browser")
    assert res == b"", res
    assert len(await admin.get_authentication_flows()) == 9

    # Test create
    res = await admin.create_authentication_flow(
        payload={"alias": "test-create", "providerId": "basic-flow"}
    )
    assert res == b""
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_authentication_flow(payload={"alias": "test-create", "builtIn": False})
    assert err.match('409: b\'{"errorMessage":"Flow test-create already exists"}\'')
    assert await admin.create_authentication_flow(
        payload={"alias": "test-create"}, skip_exists=True
    ) == {"msg": "Already exists"}

    # Test flow executions
    res = await admin.get_authentication_flow_executions(flow_alias="browser")
    assert len(res) == 8, res
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_authentication_flow_executions(flow_alias="bad")
    assert err.match("404: b''")
    exec_id = res[0]["id"]

    res = await admin.get_authentication_flow_execution(execution_id=exec_id)
    assert set(res.keys()) == {
        "alternative",
        "authenticator",
        "authenticatorFlow",
        "conditional",
        "disabled",
        "enabled",
        "id",
        "parentFlow",
        "priority",
        "required",
        "requirement",
    }, res
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_authentication_flow_execution(execution_id="bad")
    assert err.match('404: b\'{"error":"Illegal execution"}\'')

    with pytest.raises(KeycloakPostError) as err:
        await admin.create_authentication_flow_execution(payload=dict(), flow_alias="browser")
    assert err.match('400: b\'{"error":"It is illegal to add execution to a built in flow"}\'')

    res = await admin.create_authentication_flow_execution(
        payload={"provider": "auth-cookie"}, flow_alias="test-create"
    )
    assert res == b""
    assert len(await admin.get_authentication_flow_executions(flow_alias="test-create")) == 1

    with pytest.raises(KeycloakPutError) as err:
        await admin.update_authentication_flow_executions(
            payload={"required": "yes"}, flow_alias="test-create"
        )
    assert err.match('400: b\'{"error":"Unrecognized field')
    flow = await admin.get_authentication_flow_executions(flow_alias="test-create")
    payload = flow[0]
    payload["displayName"] = "test"
    res = await admin.update_authentication_flow_executions(payload=payload, flow_alias="test-create")
    assert res

    flow = await admin.get_authentication_flow_executions(flow_alias="test-create")
    exec_id = flow[0]["id"]
    res = await admin.delete_authentication_flow_execution(execution_id=exec_id)
    assert res == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_authentication_flow_execution(execution_id=exec_id)
    assert err.match('404: b\'{"error":"Illegal execution"}\'')

    # Test subflows
    res = await admin.create_authentication_flow_subflow(
        payload={
            "alias": "test-subflow",
            "provider": "basic-flow",
            "type": "something",
            "description": "something",
        },
        flow_alias="test-browser",
    )
    assert res == b""
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_authentication_flow_subflow(
            payload={"alias": "test-subflow", "providerId": "basic-flow"},
            flow_alias="test-browser",
        )
    assert err.match('409: b\'{"errorMessage":"New flow alias name already exists"}\'')
    res = await admin.create_authentication_flow_subflow(
        payload={
            "alias": "test-subflow",
            "provider": "basic-flow",
            "type": "something",
            "description": "something",
        },
        flow_alias="test-create",
        skip_exists=True,
    )
    assert res == {"msg": "Already exists"}

    # Test delete auth flow
    flow_id = [x for x in await admin.get_authentication_flows() if x["alias"] == "test-browser"][0][
        "id"
    ]
    res = await admin.delete_authentication_flow(flow_id=flow_id)
    assert res == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_authentication_flow(flow_id=flow_id)
    assert err.match('404: b\'{"error":"Could not find flow with id"}\'')


@pytest.mark.asyncio
async def test_authentication_configs(admin: KeycloakAdmin, realm: str):
    """Test authentication configs.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Test list of auth providers
    res = await admin.get_authenticator_providers()
    assert len(res) == 38

    res = await admin.get_authenticator_provider_config_description(provider_id="auth-cookie")
    assert res == {
        "helpText": "Validates the SSO cookie set by the auth server.",
        "name": "Cookie",
        "properties": [],
        "providerId": "auth-cookie",
    }

    # Test authenticator config
    # Currently unable to find a sustainable way to fetch the config id,
    # therefore testing only failures
    with pytest.raises(KeycloakGetError) as err:
        await admin.get_authenticator_config(config_id="bad")
    assert err.match('404: b\'{"error":"Could not find authenticator config"}\'')

    with pytest.raises(KeycloakPutError) as err:
        await admin.update_authenticator_config(payload=dict(), config_id="bad")
    assert err.match('404: b\'{"error":"Could not find authenticator config"}\'')

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_authenticator_config(config_id="bad")
    assert err.match('404: b\'{"error":"Could not find authenticator config"}\'')


@pytest.mark.asyncio
async def test_sync_users(admin: KeycloakAdmin, realm: str):
    """Test sync users.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Only testing the error message
    with pytest.raises(KeycloakPostError) as err:
        await admin.sync_users(storage_id="does-not-exist", action="triggerFullSync")
    assert err.match('404: b\'{"error":"Could not find component"}\'')


@pytest.mark.asyncio
async def test_client_scopes(admin: KeycloakAdmin, realm: str):
    """Test client scopes.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Test get client scopes
    res = await admin.get_client_scopes()
    scope_names = {x["name"] for x in res}
    assert len(res) == 10
    assert "email" in scope_names
    assert "profile" in scope_names
    assert "offline_access" in scope_names

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_client_scope(client_scope_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find client scope"}\'')

    scope = await admin.get_client_scope(client_scope_id=res[0]["id"])
    assert res[0] == scope

    scope = await admin.get_client_scope_by_name(client_scope_name=res[0]["name"])
    assert res[0] == scope

    # Test create client scope
    res = await admin.create_client_scope(payload={"name": "test-scope"}, skip_exists=True)
    assert res
    res2 = await admin.create_client_scope(payload={"name": "test-scope"}, skip_exists=True)
    assert res == res2
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_client_scope(payload={"name": "test-scope"}, skip_exists=False)
    assert err.match('409: b\'{"errorMessage":"Client Scope test-scope already exists"}\'')

    # Test update client scope
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_client_scope(client_scope_id="does-not-exist", payload=dict())
    assert err.match('404: b\'{"error":"Could not find client scope"}\'')

    res_update = await admin.update_client_scope(
        client_scope_id=res, payload={"name": "test-scope-update"}
    )
    assert res_update == dict()
    scope = await admin.get_client_scope(client_scope_id=res)
    scope["name"] == "test-scope-update"

    # Test get mappers
    mappers = await admin.get_mappers_from_client_scope(client_scope_id=res)
    assert mappers == list()

    # Test add mapper
    with pytest.raises(KeycloakPostError) as err:
        await admin.add_mapper_to_client_scope(client_scope_id=res, payload=dict())
    assert err.match('404: b\'{"error":"ProtocolMapper provider not found"}\'')

    res_add = await admin.add_mapper_to_client_scope(
        client_scope_id=res,
        payload={
            "name": "test-mapper",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
        },
    )
    assert res_add == b""
    assert len(await admin.get_mappers_from_client_scope(client_scope_id=res)) == 1

    # Test update mapper
    mapper = await admin.get_mappers_from_client_scope(client_scope_id=res)
    test_mapper = mapper[0]
    with pytest.raises(KeycloakPutError) as err:
        await admin.update_mapper_in_client_scope(
            client_scope_id="does-not-exist", protocol_mapper_id=test_mapper["id"], payload=dict()
        )
    assert err.match('404: b\'{"error":"Could not find client scope"}\'')
    test_mapper["config"]["user.attribute"] = "test"
    res_update = await admin.update_mapper_in_client_scope(
        client_scope_id=res, protocol_mapper_id=test_mapper["id"], payload=test_mapper
    )
    assert res_update == dict()
    mapper = await admin.get_mappers_from_client_scope(client_scope_id=res)
    assert (
        mapper[0]["config"]["user.attribute"]
        == "test"
    )

    # Test delete mapper
    res_del = await admin.delete_mapper_from_client_scope(
        client_scope_id=res, protocol_mapper_id=test_mapper["id"]
    )
    assert res_del == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_mapper_from_client_scope(
            client_scope_id=res, protocol_mapper_id=test_mapper["id"]
        )
    assert err.match('404: b\'{"error":"Model not found"}\'')

    # Test default default scopes
    res_defaults = await admin.get_default_default_client_scopes()
    assert len(res_defaults) == 6

    with pytest.raises(KeycloakPutError) as err:
        await admin.add_default_default_client_scope(scope_id="does-not-exist")
    assert err.match('404: b\'{"error":"Client scope not found"}\'')

    res_add = await admin.add_default_default_client_scope(scope_id=res)
    assert res_add == dict()
    assert len(await admin.get_default_default_client_scopes()) == 7

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_default_default_client_scope(scope_id="does-not-exist")
    assert err.match('404: b\'{"error":"Client scope not found"}\'')

    res_del = await admin.delete_default_default_client_scope(scope_id=res)
    assert res_del == dict()
    assert len(await admin.get_default_default_client_scopes()) == 6

    # Test default optional scopes
    res_defaults = await admin.get_default_optional_client_scopes()
    assert len(res_defaults) == 4

    with pytest.raises(KeycloakPutError) as err:
        await admin.add_default_optional_client_scope(scope_id="does-not-exist")
    assert err.match('404: b\'{"error":"Client scope not found"}\'')

    res_add = await admin.add_default_optional_client_scope(scope_id=res)
    assert res_add == dict()
    assert len(await admin.get_default_optional_client_scopes()) == 5

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_default_optional_client_scope(scope_id="does-not-exist")
    assert err.match('404: b\'{"error":"Client scope not found"}\'')

    res_del = await admin.delete_default_optional_client_scope(scope_id=res)
    assert res_del == dict()
    assert len(await admin.get_default_optional_client_scopes()) == 4

    # Test client scope delete
    res_del = await admin.delete_client_scope(client_scope_id=res)
    assert res_del == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_client_scope(client_scope_id=res)
    assert err.match('404: b\'{"error":"Could not find client scope"}\'')


@pytest.mark.asyncio
async def test_components(admin: KeycloakAdmin, realm: str):
    """Test components.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    # Test get components
    res = await admin.get_components()
    assert len(res) == 12

    with pytest.raises(KeycloakGetError) as err:
        await admin.get_component(component_id="does-not-exist")
    assert err.match('404: b\'{"error":"Could not find component"}\'')

    res_get = await admin.get_component(component_id=res[0]["id"])
    assert res_get == res[0]

    # Test create component
    with pytest.raises(KeycloakPostError) as err:
        await admin.create_component(payload={"bad": "dict"})
    assert err.match('400: b\'{"error":"Unrecognized field')

    res = await admin.create_component(
        payload={
            "name": "Test Component",
            "providerId": "max-clients",
            "providerType": "org.keycloak.services.clientregistration."
            + "policy.ClientRegistrationPolicy",
            "config": {"max-clients": ["1000"]},
        }
    )
    assert res
    component = await admin.get_component(component_id=res)
    assert component["name"] == "Test Component"

    # Test update component
    component = await admin.get_component(component_id=res)
    component["name"] = "Test Component Update"

    with pytest.raises(KeycloakPutError) as err:
        await admin.update_component(component_id="does-not-exist", payload=dict())
    assert err.match('404: b\'{"error":"Could not find component"}\'')
    res_upd = await admin.update_component(component_id=res, payload=component)
    assert res_upd == dict()
    component = await admin.get_component(component_id=res)
    assert component["name"] == "Test Component Update"

    # Test delete component
    res_del = await admin.delete_component(component_id=res)
    assert res_del == dict()
    with pytest.raises(KeycloakDeleteError) as err:
        await admin.delete_component(component_id=res)
    assert err.match('404: b\'{"error":"Could not find component"}\'')


@pytest.mark.asyncio
async def test_keys(admin: KeycloakAdmin, realm: str):
    """Test keys.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm
    keys = await admin.get_keys()
    assert set(keys["active"].keys()) == {"AES", "HS256", "RS256", "RSA-OAEP"}
    assert {k["algorithm"] for k in keys["keys"]} == {
        "HS256",
        "RSA-OAEP",
        "AES",
        "RS256",
    }


@pytest.mark.asyncio
async def test_events(admin: KeycloakAdmin, realm: str):
    """Test events.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm

    events = await admin.get_events()
    assert events == list()

    with pytest.raises(KeycloakPutError) as err:
        await admin.set_events(payload={"bad": "conf"})
    assert err.match('400: b\'{"error":"Unrecognized field')

    res = await admin.set_events(payload={"adminEventsDetailsEnabled": True, "adminEventsEnabled": True})
    assert res == dict()

    await admin.create_client(payload={"name": "test", "clientId": "test"})

    events = await admin.get_events()
    assert events == list()


@pytest.mark.asyncio
async def test_auto_refresh(admin: KeycloakAdmin, realm: str):
    """Test auto refresh token.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    # Test get refresh
    admin.auto_refresh_token = list()
    admin.connection = ConnectionManager(
        base_url=admin.server_url,
        headers={"Authorization": "Bearer bad", "Content-Type": "application/json"},
        timeout=60,
        verify=admin.verify,
    )

    with pytest.raises(KeycloakAuthenticationError) as err:
        await admin.get_realm(realm_name=realm)
    assert err.match('401: b\'{"error":"HTTP 401 Unauthorized"}\'')

    admin.auto_refresh_token = ["get"]
    del admin.token["refresh_token"]
    assert await admin.get_realm(realm_name=realm)

    # Test bad refresh token
    admin.connection = ConnectionManager(
        base_url=admin.server_url,
        headers={"Authorization": "Bearer bad", "Content-Type": "application/json"},
        timeout=60,
        verify=admin.verify,
    )
    admin.token["refresh_token"] = "bad"
    with pytest.raises(KeycloakPostError) as err:
        await admin.get_realm(realm_name="test-refresh")
    assert err.match(
        '400: b\'{"error":"invalid_grant","error_description":"Invalid refresh token"}\''
    )
    admin.realm_name = "master"
    await admin.get_token()
    admin.realm_name = realm

    # Test post refresh
    admin.connection = ConnectionManager(
        base_url=admin.server_url,
        headers={"Authorization": "Bearer bad", "Content-Type": "application/json"},
        timeout=60,
        verify=admin.verify,
    )
    with pytest.raises(KeycloakAuthenticationError) as err:
        await admin.create_realm(payload={"realm": "test-refresh"})
    assert err.match('401: b\'{"error":"HTTP 401 Unauthorized"}\'')

    admin.auto_refresh_token = ["get", "post"]
    admin.realm_name = "master"
    await admin.user_logout(user_id=await admin.get_user_id(username=admin.username))
    assert await admin.create_realm(payload={"realm": "test-refresh"}) == b""
    admin.realm_name = realm

    # Test update refresh
    admin.connection = ConnectionManager(
        base_url=admin.server_url,
        headers={"Authorization": "Bearer bad", "Content-Type": "application/json"},
        timeout=60,
        verify=admin.verify,
    )
    with pytest.raises(KeycloakAuthenticationError) as err:
        await admin.update_realm(realm_name="test-refresh", payload={"accountTheme": "test"})
    assert err.match('401: b\'{"error":"HTTP 401 Unauthorized"}\'')

    admin.auto_refresh_token = ["get", "post", "put"]
    assert (
        await admin.update_realm(realm_name="test-refresh", payload={"accountTheme": "test"}) == dict()
    )

    # Test delete refresh
    admin.connection = ConnectionManager(
        base_url=admin.server_url,
        headers={"Authorization": "Bearer bad", "Content-Type": "application/json"},
        timeout=60,
        verify=admin.verify,
    )
    with pytest.raises(KeycloakAuthenticationError) as err:
        await admin.delete_realm(realm_name="test-refresh")
    assert err.match('401: b\'{"error":"HTTP 401 Unauthorized"}\'')

    admin.auto_refresh_token = ["get", "post", "put", "delete"]
    assert await admin.delete_realm(realm_name="test-refresh") == dict()


@pytest.mark.asyncio
async def test_get_required_actions(admin: KeycloakAdmin, realm: str):
    """Test required actions.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm
    ractions = await admin.get_required_actions()
    assert isinstance(ractions, list)
    for ra in ractions:
        for key in [
            "alias",
            "name",
            "providerId",
            "enabled",
            "defaultAction",
            "priority",
            "config",
        ]:
            assert key in ra


@pytest.mark.asyncio
async def test_get_required_action_by_alias(admin: KeycloakAdmin, realm: str):
    """Test get required action by alias.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm
    ractions = await admin.get_required_actions()
    ra = await admin.get_required_action_by_alias("UPDATE_PASSWORD")
    assert ra in ractions
    assert ra["alias"] == "UPDATE_PASSWORD"
    assert await admin.get_required_action_by_alias("does-not-exist") is None


@pytest.mark.asyncio
async def test_update_required_action(admin: KeycloakAdmin, realm: str):
    """Test update required action.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    """
    admin.realm_name = realm
    ra = await admin.get_required_action_by_alias("UPDATE_PASSWORD")
    old = copy.deepcopy(ra)
    ra["enabled"] = False
    await admin.update_required_action("UPDATE_PASSWORD", ra)
    newra = await admin.get_required_action_by_alias("UPDATE_PASSWORD")
    assert old != newra
    assert newra["enabled"] is False


@pytest.mark.asyncio
async def test_get_composite_client_roles_of_group(
    admin: KeycloakAdmin, realm: str, client: str, group: str, composite_client_role: str
):
    """Test get composite client roles of group.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    :param client: Keycloak client
    :type client: str
    :param group: Keycloak group
    :type group: str
    :param composite_client_role: Composite client role
    :type composite_client_role: str
    """
    admin.realm_name = realm
    role = await admin.get_client_role(client, composite_client_role)
    await admin.assign_group_client_roles(group_id=group, client_id=client, roles=[role])
    result = await admin.get_composite_client_roles_of_group(client, group)
    assert role["id"] in [x["id"] for x in result]


@pytest.mark.asyncio
async def test_get_role_client_level_children(
    admin: KeycloakAdmin, realm: str, client: str, composite_client_role: str, client_role: str
):
    """Test get children of composite client role.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param realm: Keycloak realm
    :type realm: str
    :param client: Keycloak client
    :type client: str
    :param composite_client_role: Composite client role
    :type composite_client_role: str
    :param client_role: Client role
    :type client_role: str
    """
    admin.realm_name = realm
    child = await admin.get_client_role(client, client_role)
    parent = await admin.get_client_role(client, composite_client_role)
    res = await admin.get_role_client_level_children(client, parent["id"])
    assert child["id"] in [x["id"] for x in res]


#@pytest.mark.asyncio
#async def test_upload_certificate(admin: KeycloakAdmin, realm: str, client: str, selfsigned_cert: tuple):
#    """Test upload certificate.
#
#    :param admin: Keycloak Admin client
#    :type admin: KeycloakAdmin
#    :param realm: Keycloak realm
#    :type realm: str
#    :param client: Keycloak client
#    :type client: str
#    :param selfsigned_cert: Selfsigned certificates
#    :type selfsigned_cert: tuple
#    """
#    admin.realm_name = realm
#    cert, _ = selfsigned_cert
#    cert = cert.decode("utf-8").strip()
#    await admin.upload_certificate(client, cert)
#    cl = await admin.get_client(client)
#    assert cl["attributes"]["jwt.credential.certificate"] == "".join(cert.splitlines()[1:-1])


@pytest.mark.asyncio
async def test_get_bruteforce_status_for_user(
    admin: KeycloakAdmin, oid_with_credentials: Tuple[KeycloakOpenID, str, str], realm: str
):
    """Test users.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param oid_with_credentials: Keycloak OpenID client with pre-configured user credentials
    :type oid_with_credentials: Tuple[KeycloakOpenID, str, str]
    :param realm: Keycloak realm
    :type realm: str
    """
    oid, username, password = oid_with_credentials
    admin.realm_name = realm

    # Turn on bruteforce protection
    res = await admin.update_realm(realm_name=realm, payload={"bruteForceProtected": True})
    res = await admin.get_realm(realm_name=realm)
    assert res["bruteForceProtected"] is True

    # Test login user with wrong credentials
    try:
        await oid.token(username=username, password="wrongpassword")
    except KeycloakAuthenticationError:
        pass

    user_id = await admin.get_user_id(username)
    bruteforce_status = await admin.get_bruteforce_detection_status(user_id)

    assert bruteforce_status["numFailures"] == 1

    # Cleanup
    res = await admin.update_realm(realm_name=realm, payload={"bruteForceProtected": False})
    res = await admin.get_realm(realm_name=realm)
    assert res["bruteForceProtected"] is False


@pytest.mark.asyncio
async def test_clear_bruteforce_attempts_for_user(
    admin: KeycloakAdmin, oid_with_credentials: Tuple[KeycloakOpenID, str, str], realm: str
):
    """Test users.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param oid_with_credentials: Keycloak OpenID client with pre-configured user credentials
    :type oid_with_credentials: Tuple[KeycloakOpenID, str, str]
    :param realm: Keycloak realm
    :type realm: str
    """
    oid, username, password = oid_with_credentials
    admin.realm_name = realm

    # Turn on bruteforce protection
    res = await admin.update_realm(realm_name=realm, payload={"bruteForceProtected": True})
    res = await admin.get_realm(realm_name=realm)
    assert res["bruteForceProtected"] is True

    # Test login user with wrong credentials
    try:
        await oid.token(username=username, password="wrongpassword")
    except KeycloakAuthenticationError:
        pass

    user_id = await admin.get_user_id(username)
    bruteforce_status = await admin.get_bruteforce_detection_status(user_id)
    assert bruteforce_status["numFailures"] == 1

    res = await admin.clear_bruteforce_attempts_for_user(user_id)
    bruteforce_status = await admin.get_bruteforce_detection_status(user_id)
    assert bruteforce_status["numFailures"] == 0

    # Cleanup
    res = await admin.update_realm(realm_name=realm, payload={"bruteForceProtected": False})
    res = await admin.get_realm(realm_name=realm)
    assert res["bruteForceProtected"] is False


@pytest.mark.asyncio
async def test_clear_bruteforce_attempts_for_all_users(
    admin: KeycloakAdmin, oid_with_credentials: Tuple[KeycloakOpenID, str, str], realm: str
):
    """Test users.

    :param admin: Keycloak Admin client
    :type admin: KeycloakAdmin
    :param oid_with_credentials: Keycloak OpenID client with pre-configured user credentials
    :type oid_with_credentials: Tuple[KeycloakOpenID, str, str]
    :param realm: Keycloak realm
    :type realm: str
    """
    oid, username, password = oid_with_credentials
    admin.realm_name = realm

    # Turn on bruteforce protection
    res = await admin.update_realm(realm_name=realm, payload={"bruteForceProtected": True})
    res = await admin.get_realm(realm_name=realm)
    assert res["bruteForceProtected"] is True

    # Test login user with wrong credentials
    try:
        await oid.token(username=username, password="wrongpassword")
    except KeycloakAuthenticationError:
        pass

    user_id = await admin.get_user_id(username)
    bruteforce_status = await admin.get_bruteforce_detection_status(user_id)
    assert bruteforce_status["numFailures"] == 1

    res = await admin.clear_all_bruteforce_attempts()
    bruteforce_status = await admin.get_bruteforce_detection_status(user_id)
    assert bruteforce_status["numFailures"] == 0

    # Cleanup
    res = await admin.update_realm(realm_name=realm, payload={"bruteForceProtected": False})
    res = await admin.get_realm(realm_name=realm)
    assert res["bruteForceProtected"] is False


@pytest.mark.asyncio
async def test_default_realm_role_present(realm: str, admin: KeycloakAdmin) -> None:
    """Test that the default realm role is present in a brand new realm.

    :param realm: Realm name
    :type realm: str
    :param admin: Keycloak admin
    :type admin: KeycloakAdmin
    """
    admin.realm_name = realm
    assert f"default-roles-{realm}" in [x["name"] for x in await admin.get_realm_roles()]
    assert (
        len([x["name"] for x in await admin.get_realm_roles() if x["name"] == f"default-roles-{realm}"])
        == 1
    )


@pytest.mark.asyncio
async def test_get_default_realm_role_id(realm: str, admin: KeycloakAdmin) -> None:
    """Test getter for the ID of the default realm role.

    :param realm: Realm name
    :type realm: str
    :param admin: Keycloak admin
    :type admin: KeycloakAdmin
    """
    admin.realm_name = realm
    assert (
        await admin.get_default_realm_role_id()
        == [x["id"] for x in await admin.get_realm_roles() if x["name"] == f"default-roles-{realm}"][0]
    )


@pytest.mark.asyncio
async def test_realm_default_roles(admin: KeycloakAdmin, realm: str) -> None:
    """Test getting, adding and deleting default realm roles.

    :param realm: Realm name
    :type realm: str
    :param admin: Keycloak admin
    :type admin: KeycloakAdmin
    """
    admin.realm_name = realm

    # Test listing all default realm roles
    roles = await admin.get_realm_default_roles()
    assert len(roles) == 2
    assert {x["name"] for x in roles} == {"offline_access", "uma_authorization"}

    with pytest.raises(KeycloakGetError) as err:
        admin.realm_name = "doesnotexist"
        await admin.get_realm_default_roles()
    assert err.match('404: b\'{"error":"Realm not found."}\'')
    admin.realm_name = realm

    # Test removing a default realm role
    res = await admin.remove_realm_default_roles(payload=[roles[0]])
    assert res == {}
    assert roles[0] not in await admin.get_realm_default_roles()
    assert len(await admin.get_realm_default_roles()) == 1

    with pytest.raises(KeycloakDeleteError) as err:
        await admin.remove_realm_default_roles(payload=[{"id": "bad id"}])
    assert err.match('404: b\'{"error":"Could not find composite role"}\'')

    # Test adding a default realm role
    res = await admin.add_realm_default_roles(payload=[roles[0]])
    assert res == {}
    assert roles[0] in await admin.get_realm_default_roles()
    assert len(await admin.get_realm_default_roles()) == 2

    with pytest.raises(KeycloakPostError) as err:
        await admin.add_realm_default_roles(payload=[{"id": "bad id"}])
    assert err.match('404: b\'{"error":"Could not find composite role"}\'')
