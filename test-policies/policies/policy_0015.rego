package audit.authorization.context.allow.core.policy_0015

# Auto-generated policy 15 (Rego v1 syntax)
# Package: audit.authorization.context.allow.core

# Metadata
metadata := {
    "policy_id": "0015",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0015_allowed = false
policy_0015_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0015_allowed if {
    input.user.active
    input.resource.public
}
policy_0015_allowed if {
    data.policies.audit.enabled
}
