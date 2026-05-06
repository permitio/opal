package governance.authentication.policy.verify.helpers.policy_0142

# Auto-generated policy 142 (Rego v1 syntax)
# Package: governance.authentication.policy.verify.helpers

# Metadata
metadata := {
    "policy_id": "0142",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0142_allowed if {
    data.policies.governance.enabled
}
policy_0142_allowed if {
    input.user.role == "admin"
}
