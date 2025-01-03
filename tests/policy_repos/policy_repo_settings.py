# class PolicyRepoSettings:
#     repo_name = "opal-example-policy-repo"
#     branch_name = "main"
#     temp_dir = "/tmp/opal-example-policy-repo"
#     username = "opal"
#     port_http = 3000
#     port_ssh = 3001
#     gitea_base_url = f"http://localhost:{port_http}"
#     github_base_url = "https://github.com"
#     github_token = "ghp_abc123"
#     github_owner = "opal"
#     github_repo = "opal-examaple-policy-repo"
#     gitea_owner = "opal"
#     gitea_repo = "opal-example-policy-repo"
#     gitea_token
#     gitea_username = "opal"
#     gitea_password = "password"
#     github_username = "opal"
#     github_password = "password"
#     gitea_repo_url = f"{gitea_base_url}/{gitea_owner}/{gitea_repo}.git"
#     github_repo_url = f"{github_base_url}/{github_owner}/{github_repo}.git"
#     github_repo_url_with_token = f"{github_base_url}/{github_owner}/{github_repo}.git"
#     gitea_repo_url_with_token = f"{gitea_base_url}/{gitea_owner}/{gitea_repo}.git"
#     commit_message = "Update policy"
#     file_name = "policy.json"
#     file_content = """
#     {
#         "source_type": "git",
#         "url": "https://github.com/permitio/opal-example-policy-repo",
#         "auth": {
#             "auth_type": "none"
#         },
#         "extensions": [
#             {
#                 "name": "cedar",
#                 "source_type": "git",
#                 "url": "https://github.com/permitio/opal-example-policy-repo",
#                 "auth": {
#                     "auth_type": "none"
#                 }
#             }
#         ]
#     }
#     """
#     file_content_gitea = """
#     {
#         "source_type": "git",
#         "url": "https://localhost:3000/opal/opal-example-policy-repo",
#         "auth": {
#             "auth_type": "none"
#         },
#         "extensions": [
#             {
#                 "name": "cedar",
#                 "source_type": "git",
#                 "url": "https://localhost:3000/opal/opal-example-policy-repo",
#                 "auth": {
#                     "auth_type": "none"
#                 }
#             }
#         ]
#     }
#     """
#     file_content_github = """
#     {
#         "source_type": "git",
#         "url": "https://github.com/opal/opal-example-policy-repo",
#         "auth": {
#             "auth_type": "none"
#         },
#         "extensions": [
#             {
#                 "name": "cedar",
#                 "source_type": "git",
#                 "url": "https://github.com/opal/opal-example-policy-repo",
#                 "auth": {
#                     "auth_type": "none"
#                 }
#             }
#         ]
#     }
#     """
#     file_content_github_with_token = """
#     {
#         "source_type": "git",
#         "url": "https://github.com/opal/opal-example-policy-repo",
#         "auth": {
#             "auth_type": "github_token",
#             "token": "ghp_abc123"
#         },
#         "extensions": [
#             {
#                 "name": "cedar",
#                 "source_type": "git",
#                 "url": "https://github.com/opal/opal-example-policy-repo",
#                 "auth": {
#                     "auth_type": "github_token",
#                     "token": "ghp_abc123"
#                 }
#             }]
#                 }
