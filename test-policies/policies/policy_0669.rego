package governance.authorization.policy.verify.policy_0669

# Auto-generated policy 669 (Rego v1 syntax)
# Package: governance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0669",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0669_allowed = false
policy_0669_allowed if {
    input.user.active
    input.resource.public
}
