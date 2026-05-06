package risk.validation.user.allow.core.policy_0408

# Auto-generated policy 408 (Rego v1 syntax)
# Package: risk.validation.user.allow.core

# Metadata
metadata := {
    "policy_id": "0408",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0408_allowed if {
    input.user.active
    input.resource.public
}
policy_0408_allowed if {
    input.user.role == "admin"
}
policy_0408_allowed if {
    data.policies.risk.enabled
}
