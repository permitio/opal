package governance.authentication.context.allow.policy_0829

# Auto-generated policy 829 (Rego v1 syntax)
# Package: governance.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0829",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0829_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0829_allowed if {
    input.user.active
    input.resource.public
}
policy_0829_allowed if {
    data.policies.governance.enabled
}
default policy_0829_allowed = false
