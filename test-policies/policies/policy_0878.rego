package compliance.authentication.action.check.policy_0878

# Auto-generated policy 878 (Rego v1 syntax)
# Package: compliance.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0878",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0878_allowed if {
    data.policies.compliance.enabled
}
policy_0878_allowed if {
    input.user.role == "admin"
}
