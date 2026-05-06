package compliance.authentication.resource.check.data.policy_0738

# Auto-generated policy 738 (Rego v1 syntax)
# Package: compliance.authentication.resource.check.data

# Metadata
metadata := {
    "policy_id": "0738",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0738_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0738_allowed if {
    input.user.role == "admin"
}
