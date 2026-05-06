package compliance.authentication.user.verify.policy_0314

# Auto-generated policy 314 (Rego v1 syntax)
# Package: compliance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0314",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0314_allowed if {
    input.user.active
    input.resource.public
}
policy_0314_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
