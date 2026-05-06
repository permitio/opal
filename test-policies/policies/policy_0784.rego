package audit.authorization.resource.allow.policy_0784

# Auto-generated policy 784 (Rego v1 syntax)
# Package: audit.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0784",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0784_allowed if {
    data.policies.audit.enabled
}
policy_0784_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0784_allowed if {
    input.user.active
    input.resource.public
}
