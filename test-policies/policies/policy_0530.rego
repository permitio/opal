package compliance.validation.user.check.policy_0530

# Auto-generated policy 530 (Rego v1 syntax)
# Package: compliance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0530",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0530_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0530_allowed if {
    data.policies.compliance.enabled
}
policy_0530_allowed if {
    input.user.role == "admin"
}
