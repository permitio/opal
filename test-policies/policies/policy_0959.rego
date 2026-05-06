package compliance.authorization.action.deny.policy_0959

# Auto-generated policy 959 (Rego v1 syntax)
# Package: compliance.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0959",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0959_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0959_allowed if {
    data.policies.compliance.enabled
}
policy_0959_allowed if {
    input.user.active
    input.resource.public
}
