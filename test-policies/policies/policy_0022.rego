package compliance.authorization.policy.deny.policy_0022

# Auto-generated policy 22 (Rego v1 syntax)
# Package: compliance.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0022",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0022_allowed = false
policy_0022_allowed if {
    data.policies.compliance.enabled
}
policy_0022_allowed if {
    input.user.role == "admin"
}
