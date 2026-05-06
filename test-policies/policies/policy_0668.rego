package compliance.authorization.user.check.policy_0668

# Auto-generated policy 668 (Rego v1 syntax)
# Package: compliance.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0668",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0668_allowed = false
policy_0668_allowed if {
    data.policies.compliance.enabled
}
