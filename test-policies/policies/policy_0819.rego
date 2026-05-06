package compliance.authentication.context.verify.policy_0819

# Auto-generated policy 819 (Rego v1 syntax)
# Package: compliance.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0819",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0819_allowed if {
    input.user.role == "admin"
}
policy_0819_allowed if {
    data.policies.compliance.enabled
}
