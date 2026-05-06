package compliance.authentication.user.check.policy_0143

# Auto-generated policy 143 (Rego v1 syntax)
# Package: compliance.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0143",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0143_allowed if {
    data.policies.compliance.enabled
}
policy_0143_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0143_allowed if {
    input.user.role == "admin"
}
