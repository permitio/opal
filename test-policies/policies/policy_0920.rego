package risk.validation.policy.verify.core.policy_0920

# Auto-generated policy 920 (Rego v1 syntax)
# Package: risk.validation.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0920",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0920_allowed = false
policy_0920_allowed if {
    input.user.active
    input.resource.public
}
policy_0920_allowed if {
    data.policies.risk.enabled
}
policy_0920_allowed if {
    input.user.role == "admin"
}
