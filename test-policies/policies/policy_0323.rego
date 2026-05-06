package governance.validation.policy.check.policy_0323

# Auto-generated policy 323 (Rego v1 syntax)
# Package: governance.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0323",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0323_allowed if {
    input.user.active
    input.resource.public
}
default policy_0323_allowed = false
