package audit.authentication.context.verify.core.policy_0986

# Auto-generated policy 986 (Rego v1 syntax)
# Package: audit.authentication.context.verify.core

# Metadata
metadata := {
    "policy_id": "0986",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0986_allowed if {
    data.policies.audit.enabled
}
policy_0986_allowed if {
    input.user.active
    input.resource.public
}
policy_0986_allowed if {
    input.user.role == "admin"
}
default policy_0986_allowed = false
